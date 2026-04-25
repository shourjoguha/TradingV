"""Sync outbox orchestration.

Two row kinds share one queue:

- ``kind='ticker'`` — pushes (symbol, asset_class) to peer ``/v1/tickers``.
  Enqueued by :func:`enqueue` after each completed analysis job.
- ``kind='result'`` — pushes a full job snapshot to peer ``/v1/analysis/import``.
  Enqueued by :func:`enqueue_result` after each completed analysis job.

``drain_outbox()`` picks up rows where ``next_retry_at <= now()`` and
``completed_at IS NULL``, dispatches by kind, and applies the same
exponential-backoff retry policy on failure (30s × 2^attempts, capped 1h).

The receiver is idempotent for both kinds — duplicate pushes are safe.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable

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
    """Insert ``kind='ticker'`` rows for (symbol, asset_class) pairs.

    Returns count enqueued. No-op if peer not configured.
    """
    if not peer_configured():
        logger.debug("sync: peer not configured, skipping ticker enqueue")
        return 0

    peer_url = SETTINGS.PEER_API_URL
    rows: list[SyncOutbox] = []
    for symbol, asset_class in tickers:
        rows.append(
            SyncOutbox(
                peer_url=peer_url,
                kind="ticker",
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


async def enqueue_result(payload: dict[str, Any]) -> int:
    """Insert one ``kind='result'`` row carrying a full job snapshot.

    ``payload`` shape::

        {
          "schema_version": 1,
          "origin": "<INSTANCE_NAME>",
          "job": {... AnalysisJob serialised ...},
          "tasks": [... AnalysisTask serialised ...],
        }

    Returns 1 on enqueue, 0 if peer not configured.
    """
    if not peer_configured():
        logger.debug("sync: peer not configured, skipping result enqueue")
        return 0

    row = SyncOutbox(
        peer_url=SETTINGS.PEER_API_URL,
        kind="result",
        payload_json=payload,
    )
    async with _db.SessionLocal() as session:
        session.add(row)
        await session.commit()
    return 1


async def drain_outbox(*, max_rows: int = 100) -> dict[str, int]:
    """Attempt to push every pending row whose next_retry_at has passed.

    Branches on ``kind``: ticker rows → :func:`peer_client.push_ticker`;
    result rows → :func:`peer_client.push_result`. Returns counters:
    ``{"ok", "failed", "scanned"}``.
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
            kind = row.kind or "ticker"
            if kind == "ticker":
                ok, err = await peer_client.push_ticker(
                    peer_url=row.peer_url,
                    api_key=api_key,
                    symbol=row.symbol or "",
                    asset_class=row.asset_class or "unknown",
                )
            elif kind == "result":
                ok, err = await peer_client.push_result(
                    peer_url=row.peer_url,
                    api_key=api_key,
                    payload=row.payload_json or {},
                )
            else:
                ok, err = False, f"unknown_kind: {kind}"

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
