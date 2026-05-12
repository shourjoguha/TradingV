"""Weekly auto-stress task. Fires once per active hypothesis per week,
writes one-line summaries into the vault's `_review-queue.md` so unread
answer files surface in the operator's tick-discipline pass.

Wired into app/main.py lifespan.

Steering: hypotheses are pre-ranked by at-risk status (TTL ≤ 30d) and
days-to-expire so the urgent ones get stress-tested first. Each tick
appends a structured event log to ``<vault>/Research/_steering-log.md``
for operator audit (the file starts with ``_`` so the indexer skips it —
diagnostic, not embedded knowledge)."""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.core import db as _db
from app.hypotheses import service as hyp_service
from app.hypotheses.models import STATUS_ACTIVE
from app.research import service as _service

logger = logging.getLogger(__name__)


VAULT_PATH = Path(os.environ.get("VAULT_PATH", str(Path.home() / "Documents" / "knowledge-vault")))
SLEEP_SECONDS = int(os.environ.get("RESEARCH_WEEKLY_SLEEP_SECONDS", str(7 * 24 * 60 * 60)))
WARMUP_SECONDS = int(os.environ.get("RESEARCH_WEEKLY_WARMUP_SECONDS", str(60 * 60)))

# A hypothesis is at-risk when its expires_at is within this many days.
# Matches the hypotheses summary endpoint convention.
AT_RISK_DAYS = 30


DEFAULT_QUERY = (
    "What is the strongest counterargument or risk to this thesis based on "
    "recent vault content + current macro state? Propose a concrete invalidator "
    "tightening if the evidence supports it."
)


def _rank_active(
    active: list, now: datetime.datetime
) -> list[tuple[Any, dict]]:
    """Return ``[(hypothesis, priority_meta), ...]`` sorted urgency-first.

    Sort key:
      1. ``is_at_risk DESC`` — TTL ≤ 30d goes first
      2. ``days_to_expire ASC`` — within at-risk, soonest first
      3. ``slug ASC`` — stable tiebreak
    """
    cutoff = now + datetime.timedelta(days=AT_RISK_DAYS)
    enriched: list[tuple[Any, dict]] = []
    for h in active:
        # Hypothesis.expires_at may be tz-aware or naive depending on the DB
        # adapter; normalise to UTC-aware for the diff.
        expires = h.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        days_to_expire = (
            (expires - now).days if expires is not None else None
        )
        is_at_risk = (
            expires is not None and expires < cutoff
        )
        meta = {
            "is_at_risk": is_at_risk,
            "days_to_expire": days_to_expire,
            "priority_reason": (
                "at_risk" if is_at_risk else "scheduled"
            ),
        }
        enriched.append((h, meta))

    # Negate booleans for ascending sort = at-risk first; days_to_expire
    # may be None (no expiry) → push to the end.
    def _sort_key(item: tuple[Any, dict]) -> tuple:
        h, meta = item
        days = meta["days_to_expire"]
        return (
            0 if meta["is_at_risk"] else 1,
            days if days is not None else 10**9,
            getattr(h, "slug", ""),
        )

    enriched.sort(key=_sort_key)
    return enriched


async def run_once(*, force: bool = False) -> dict:
    """Fire one stress-test per active hypothesis, urgency-first.

    Cost-aware (Phase 4 C1/C2). Reads admin settings on every tick:
      • ``research_weekly.enabled`` (default False) — entire tick skips when off
      • ``research_weekly.scope`` (``at_risk`` | ``all``; default ``at_risk``)
      • ``research_weekly.dedupe_days`` (default 30) — skip a hypothesis whose
        most recent research_query is younger than this many days, so the
        operator's review queue doesn't refill faster than they can clear it
      • ``research_weekly.max_per_tick`` (default 3) — backlog cap

    ``force=True`` (manual-fire path) bypasses the enabled gate but still
    respects scope, dedupe, and max-per-tick.

    Side effects:
      * Appends `_review-queue.md` summary block (operator workflow).
      * Appends `_steering-log.md` structured event block (audit).
    """
    from app.admin import service as _admin_svc
    from sqlalchemy import select, func
    from app.research.models import ResearchQuery

    run_started_at = datetime.datetime.now(datetime.timezone.utc)
    stats = {
        "hypotheses": 0,
        "ok": 0,
        "errors": 0,
        "at_risk_first": 0,
        "skipped_disabled": 0,
        "skipped_scope": 0,
        "skipped_dedupe": 0,
        "skipped_backlog": 0,
    }

    enabled = await _admin_svc.get_setting("research_weekly.enabled", False)
    if not bool(enabled) and not force:
        stats["skipped_disabled"] = 1
        return stats

    scope = str(
        await _admin_svc.get_setting("research_weekly.scope", "at_risk") or "at_risk"
    ).lower()
    dedupe_days = int(
        await _admin_svc.get_setting("research_weekly.dedupe_days", 30) or 30
    )
    max_per_tick = int(
        await _admin_svc.get_setting("research_weekly.max_per_tick", 3) or 3
    )
    dedupe_cutoff = run_started_at - datetime.timedelta(days=dedupe_days)

    async with _db.SessionLocal() as session:
        active = await hyp_service.list_(session, status=STATUS_ACTIVE)
        # Pull the latest asked_at per hypothesis_id so we can dedupe.
        # `hypothesis_ids` is a JSON column; Postgres has @> but we keep this
        # backend-agnostic by loading recent rows and grouping in Python.
        recent_rows = (
            await session.execute(
                select(ResearchQuery.hypothesis_ids, ResearchQuery.asked_at)
                .where(ResearchQuery.asked_at >= dedupe_cutoff)
            )
        ).all()
    last_asked_by_slug: dict[str, datetime.datetime] = {}
    for hyp_ids, asked_at in recent_rows:
        if not hyp_ids:
            continue
        for slug in hyp_ids:
            existing = last_asked_by_slug.get(slug)
            if existing is None or asked_at > existing:
                last_asked_by_slug[slug] = asked_at

    stats["hypotheses"] = len(active)
    ranked = _rank_active(active, now=run_started_at)
    stats["at_risk_first"] = sum(1 for _, m in ranked if m["is_at_risk"])

    # Phase 4 C2: scope filter. Default at_risk so monthly auto-runs only fire
    # for hypotheses about to expire — operator can flip to `all` from the
    # admin settings if they want a wider sweep.
    if scope == "at_risk":
        before = len(ranked)
        ranked = [(h, m) for h, m in ranked if m["is_at_risk"]]
        stats["skipped_scope"] = before - len(ranked)

    # Dedupe: skip any hypothesis whose latest research_query is younger
    # than dedupe_days. Prevents refilling the review queue.
    deduped: list[tuple[Any, dict]] = []
    for h, meta in ranked:
        last_at = last_asked_by_slug.get(h.slug)
        if last_at is not None:
            stats["skipped_dedupe"] += 1
            continue
        deduped.append((h, meta))
    ranked = deduped

    # Backlog cap. Process at most max_per_tick hypotheses per run; the rest
    # roll into the next tick. Operator can drain manually via /research.
    if len(ranked) > max_per_tick:
        stats["skipped_backlog"] = len(ranked) - max_per_tick
        ranked = ranked[:max_per_tick]

    summaries: list[str] = []
    events: list[dict[str, Any]] = []

    for idx, (h, meta) in enumerate(ranked):
        event: dict[str, Any] = {
            "rank": idx + 1,
            "slug": h.slug,
            "priority_reason": meta["priority_reason"],
            "is_at_risk": meta["is_at_risk"],
            "days_to_expire": meta["days_to_expire"],
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        try:
            result = await _service.ask(
                query=DEFAULT_QUERY,
                hypothesis_slugs=[h.slug],
            )
            stats["ok"] += 1
            verdict = (result.get("verdict") or "").splitlines()[0][:200]
            event.update(
                {
                    "status": "ok",
                    "answer_path": result.get("answer_path"),
                    "verdict": verdict,
                    "research_query_id": result.get("query_id"),
                }
            )
            summaries.append(
                f"- [[{result.get('answer_path')}]] — {h.slug}: {verdict or '(no verdict)'}"
            )
        except Exception as e:                          # noqa: BLE001
            logger.warning("weekly stress failed for %s: %s", h.slug, e)
            stats["errors"] += 1
            event.update({"status": "error", "error": str(e)})
        events.append(event)

    if summaries:
        _append_to_review_queue(summaries)
    if events:
        _append_to_steering_log(events=events, run_started_at=run_started_at, stats=stats)
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


def _append_to_steering_log(
    *,
    events: list[dict[str, Any]],
    run_started_at: datetime.datetime,
    stats: dict[str, int],
) -> None:
    """Append one section per run to ``<vault>/Research/_steering-log.md``.

    The file is gitignorable + diagnostic. Each section contains a one-line
    summary, a markdown table for at-a-glance scan, and a fenced JSON
    block with the full event records for tooling. Folder + file created
    on first use.
    """
    research_dir = VAULT_PATH / "Research"
    research_dir.mkdir(parents=True, exist_ok=True)
    target = research_dir / "_steering-log.md"
    if not target.exists():
        target.write_text(
            "# Research weekly steering log\n\n"
            "Diagnostic log of every weekly stress-test tick. Operator-\n"
            "inspectable; not part of the embedded knowledge (filename starts\n"
            "with `_` so the indexer skips it).\n\n"
            "Each section: one tick. Hypotheses are processed urgency-first\n"
            "(at-risk = TTL within 30 days). The fenced JSON block is the\n"
            "machine-readable log; the table is for human scan.\n",
            encoding="utf-8",
        )

    iso = run_started_at.isoformat()
    summary = (
        f"hypotheses={stats['hypotheses']} "
        f"at_risk_first={stats['at_risk_first']} "
        f"ok={stats['ok']} errors={stats['errors']}"
    )

    table_lines = [
        "| Rank | Slug | Priority | At-risk | Days to expire | Status | Verdict |",
        "|---:|---|---|:---:|---:|:---:|---|",
    ]
    for ev in events:
        verdict_cell = (ev.get("verdict") or "")[:90].replace("|", "\\|")
        if ev.get("status") == "error":
            verdict_cell = f"⚠ {ev.get('error', '')[:80].replace('|', '\\|')}"
        days = ev.get("days_to_expire")
        days_cell = "∞" if days is None else str(days)
        table_lines.append(
            f"| {ev['rank']} | `{ev['slug']}` | {ev['priority_reason']} | "
            f"{'✓' if ev['is_at_risk'] else ''} | {days_cell} | "
            f"{ev.get('status', '?')} | {verdict_cell} |"
        )

    block = (
        f"\n## {iso}\n\n"
        f"_{summary}_\n\n"
        + "\n".join(table_lines)
        + "\n\n```json\n"
        + json.dumps(
            {"run_started_at": iso, "stats": stats, "events": events},
            indent=2,
            sort_keys=False,
        )
        + "\n```\n"
    )
    with target.open("a", encoding="utf-8") as f:
        f.write(block)


async def loop(stop_event: asyncio.Event) -> None:
    """Background task. Cadence is editable via the Admin UI:
    ``app_settings.loop.cadence.research_weekly`` (default = monthly per
    Phase 4 cost-guard C1). Loop is also gated by
    ``app_settings.loop.enabled.research_weekly`` (default False).
    """
    from app.admin import service as _admin_svc

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
        # Re-read cadence on every iteration so operator edits take effect
        # without restart. Default 30d (monthly) per cost-guard C1.
        try:
            cadence = await _admin_svc.get_setting(
                "loop.cadence.research_weekly", 30 * 24 * 60 * 60
            )
            sleep_seconds = int(cadence) if cadence else SLEEP_SECONDS
        except Exception:                               # noqa: BLE001
            sleep_seconds = SLEEP_SECONDS
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
            if stop_event.is_set():
                return
        except asyncio.TimeoutError:
            continue
