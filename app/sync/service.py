"""Sync outbox orchestration.

Flow:
1. Completed analysis jobs call `enqueue(tickers)` — one outbox row per
   unique ticker.
2. `drain_outbox()` runs in the background (fire-and-forget task at end
   of job, plus once on startup, plus on manual trigger). It picks up
   rows with `next_retry_at <= now()` and completed_at IS NULL.
3. For each row: call peer_client.push_ticker. On success mark complete.
   On failure bump `attempts`, record error, push `next_retry_at` out by
   exponential backoff (30s * 2^attempts, capped at 1 hour).

The peer receives via existing `POST /v1/tickers` (reused), but we mark
locally that these rows were emitted so ops can inspect.
"""
from __future__ import annotations

import datetime
import logging
from typing import Iterable

from sqlalchemy import select

from app.core import db as _db
from app.core.config import SETTINGS
from app.sync import peer_client
from app.sync.models import SyncOutbox

logger = logging.getLogger(__name__)

_MAX_BACKOFF_SECONDS = 3600
_BASE_BACKOFF_SECONDS = 30


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _backoff(attempts: int) -> datetime.datetime:
    """Exponential: 30s, 60s, 120s, 240s, ... capped at 1h."""
    delay = min(_BASE_BACKOFF_SECONDS * (2 ** max(attempts - 1, 0)), _MAX_BACKOFF_SECONDS)
    return _now() + datetime.timedelta(seconds=delay)


def peer_configured() -> bool:
    return bool(SETTINGS.PEER_API_URL and SETTINGS.PEER_API_KEY)


async def enqueue(tickers: Iterable[tuple[str, str]]) -> int:
    """Insert outbox rows for (symbol, asset_class) pairs. Returns count."""
    if not peer_configured():
        logger.debug("sync: peer not configured, skipping enqueue")
        return 0

    peer_url = SETTINGS.PEER_API_URL
    rows: list[SyncOutbox] = []
    for symbol, asset_class in tickers:
        rows.append(
            SyncOutbox(
                peer_url=peer_url,
                symbol=symbol,
                asset_class=asset_class,
            )
        )
    if not rows:
        return 0
    async with _db.SessionLocal() as session:
        session.add_all(rows)
        await session.commit()
    return len(rows)


async def drain_outbox(*, max_rows: int = 100) -> dict[str, int]:
    """Attempt to push every pending row whose next_retry_at has passed.

    Returns counters: {"ok": n, "failed": n, "scanned": n}.
    """
    if not peer_configured():
        return {"ok": 0, "failed": 0, "scanned": 0}

    stats = {"ok": 0, "failed": 0, "scanned": 0}
    api_key = SETTINGS.PEER_API_KEY

    async with _db.SessionLocal() as session:
        result = await session.execute(
            select(SyncOutbox)
            .where(SyncOutbox.completed_at.is_(None))
            .where(SyncOutbox.next_retry_at <= _now())
            .order_by(SyncOutbox.created_at)
            .limit(max_rows)
        )
        pending = list(result.scalars().all())
        stats["scanned"] = len(pending)

        for row in pending:
            ok, err = await peer_client.push_ticker(
                peer_url=row.peer_url,
                api_key=api_key,
                symbol=row.symbol,
                asset_class=row.asset_class,
            )
            row.attempts += 1
            if ok:
                row.completed_at = _now()
                row.last_error = None
                stats["ok"] += 1
            else:
                row.last_error = err
                row.next_retry_at = _backoff(row.attempts)
                stats["failed"] += 1

        await session.commit()

    return stats


async def list_outbox(*, status: str = "pending", limit: int = 200) -> list[SyncOutbox]:
    """status = pending | completed | failed (pending w/ attempts > 0)."""
    async with _db.SessionLocal() as session:
        stmt = select(SyncOutbox).order_by(SyncOutbox.created_at.desc()).limit(limit)
        if status == "pending":
            stmt = stmt.where(SyncOutbox.completed_at.is_(None))
        elif status == "completed":
            stmt = stmt.where(SyncOutbox.completed_at.is_not(None))
        elif status == "failed":
            stmt = stmt.where(SyncOutbox.completed_at.is_(None)).where(
                SyncOutbox.attempts > 0
            )
        result = await session.execute(stmt)
        return list(result.scalars().all())
