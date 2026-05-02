"""Weekly auto-stress task. Fires once per active hypothesis per week,
writes one-line summaries into the vault's `_review-queue.md` so unread
answer files surface in the operator's tick-discipline pass.

Wired into app/main.py lifespan."""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
from pathlib import Path

from app.core import db as _db
from app.hypotheses import service as hyp_service
from app.hypotheses.models import STATUS_ACTIVE
from app.research import service as _service

logger = logging.getLogger(__name__)


VAULT_PATH = Path(os.environ.get("VAULT_PATH", str(Path.home() / "Documents" / "knowledge-vault")))
SLEEP_SECONDS = int(os.environ.get("RESEARCH_WEEKLY_SLEEP_SECONDS", str(7 * 24 * 60 * 60)))
WARMUP_SECONDS = int(os.environ.get("RESEARCH_WEEKLY_WARMUP_SECONDS", str(60 * 60)))


DEFAULT_QUERY = (
    "What is the strongest counterargument or risk to this thesis based on "
    "recent vault content + current macro state? Propose a concrete invalidator "
    "tightening if the evidence supports it."
)


async def run_once() -> dict:
    """Fire one stress-test per active hypothesis. Append summaries to
    `_review-queue.md` if it exists."""
    stats = {"hypotheses": 0, "ok": 0, "errors": 0}
    async with _db.SessionLocal() as session:
        active = await hyp_service.list_(session, status=STATUS_ACTIVE)
    stats["hypotheses"] = len(active)
    summaries: list[str] = []
    for h in active:
        try:
            result = await _service.ask(
                query=DEFAULT_QUERY,
                hypothesis_slugs=[h.slug],
            )
            stats["ok"] += 1
            verdict = (result.get("verdict") or "").splitlines()[0][:200]
            summaries.append(
                f"- [[{result.get('answer_path')}]] — {h.slug}: {verdict or '(no verdict)'}"
            )
        except Exception as e:                          # noqa: BLE001
            logger.warning("weekly stress failed for %s: %s", h.slug, e)
            stats["errors"] += 1

    if summaries:
        _append_to_review_queue(summaries)
    return stats


def _append_to_review_queue(summary_lines: list[str]) -> None:
    target = VAULT_PATH / "_review-queue.md"
    if not target.exists():
        return
    block = (
        f"\n## Weekly stress-tests — {datetime.date.today().isoformat()}\n\n"
        + "\n".join(summary_lines)
        + "\n"
    )
    with target.open("a", encoding="utf-8") as f:
        f.write(block)


async def loop(stop_event: asyncio.Event) -> None:
    """Background task. Sleeps WARMUP_SECONDS, then runs every SLEEP_SECONDS."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=WARMUP_SECONDS)
        if stop_event.is_set():
            return
    except asyncio.TimeoutError:
        pass
    while True:
        try:
            stats = await run_once()
            logger.info("research weekly stress: %s", stats)
        except asyncio.CancelledError:
            raise
        except Exception as e:                          # noqa: BLE001
            logger.warning("weekly stress tick failed: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SLEEP_SECONDS)
            if stop_event.is_set():
                return
        except asyncio.TimeoutError:
            continue
