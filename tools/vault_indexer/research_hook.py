"""Scan ``Research/*.md`` files for ticked Approve/Dismiss boxes.

When a checkbox is ticked, the indexer's promote loop calls TradingView's
``POST /v1/research/queries/{id}/approve`` (or ``/dismiss``) using the
``research_query_id`` baked into the file's frontmatter. Same tick-to-
promote contract as ``_review-queue.md``.

Indexer needs ``TRADINGVIEW_API_URL`` and ``TRADINGVIEW_API_KEY`` env vars.
Without them the hook stays silent (no error) so a vault without a backend
still functions.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Iterable, Optional

import frontmatter
import httpx


logger = logging.getLogger(__name__)

RESEARCH_FOLDER = "Research"
TRADINGVIEW_URL = os.environ.get("TRADINGVIEW_API_URL", "http://localhost:8000")
TRADINGVIEW_KEY = os.environ.get("TRADINGVIEW_API_KEY", "")

_APPROVE_TICKED = re.compile(r"^\s*-\s*\[x\].*\bApprove\b", re.IGNORECASE)
_DISMISS_TICKED = re.compile(r"^\s*-\s*\[x\].*\bDismiss\b", re.IGNORECASE)
_APPLIED_BANNER = "<!-- vault-indexer:applied -->"


def _research_files(vault_root: Path) -> Iterable[Path]:
    research_dir = vault_root / RESEARCH_FOLDER
    if not research_dir.is_dir():
        return []
    return sorted(research_dir.glob("*.md"))


def _detect_tick(text: str) -> Optional[str]:
    """Return 'approve' or 'dismiss' for the first ticked action checkbox.
    None if no tick. None if already applied (banner present)."""
    if _APPLIED_BANNER in text:
        return None
    for line in text.splitlines():
        if _APPROVE_TICKED.match(line):
            return "approve"
        if _DISMISS_TICKED.match(line):
            return "dismiss"
    return None


def _query_id_from(path: Path) -> Optional[str]:
    try:
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
    except Exception:                                  # noqa: BLE001
        return None
    qid = post.metadata.get("research_query_id")
    return str(qid) if qid else None


def _stamp_applied(path: Path, action: str, response: dict) -> None:
    """Append a marker so we don't re-apply on the next watch event."""
    text = path.read_text(encoding="utf-8")
    banner = f"\n{_APPLIED_BANNER}\n*Applied: {action} — response: {response}*\n"
    path.write_text(text + banner, encoding="utf-8")


def scan_and_apply(vault_root: Path) -> dict:
    """Walk Research/*.md, fire approve/dismiss on each ticked file.

    Returns counts. Failures are logged + counted, not raised.
    """
    counts = {"scanned": 0, "approved": 0, "dismissed": 0, "errors": 0, "skipped": 0}

    if not TRADINGVIEW_KEY:
        return counts

    headers = {"X-API-Key": TRADINGVIEW_KEY}
    with httpx.Client(timeout=10.0) as http:
        for path in _research_files(vault_root):
            counts["scanned"] += 1
            text = path.read_text(encoding="utf-8")
            action = _detect_tick(text)
            if action is None:
                counts["skipped"] += 1
                continue
            qid = _query_id_from(path)
            if not qid:
                counts["errors"] += 1
                continue
            url = f"{TRADINGVIEW_URL}/v1/research/queries/{qid}/{action}"
            try:
                r = http.post(url, headers=headers)
                if r.status_code >= 400:
                    counts["errors"] += 1
                    logger.warning(
                        "research-hook %s %s → %s %s",
                        action, qid, r.status_code, r.text[:200],
                    )
                    continue
                _stamp_applied(path, action, r.json())
                if action == "approve":
                    counts["approved"] += 1
                else:
                    counts["dismissed"] += 1
            except Exception as e:                      # noqa: BLE001
                counts["errors"] += 1
                logger.warning("research-hook call failed: %s", e)
    return counts
