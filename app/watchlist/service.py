"""Watchlist service.

Auto-upserts the symbol into the ``tickers`` registry on add (so a brand-new
ticker can be added to the watchlist without separate POST /v1/tickers).

Replication: every external CRUD enqueues a ``kind='watchlist'`` outbox row
so the peer backend stays in sync. The ``apply_imported_*`` helpers below
write directly without enqueueing — used by ``POST /v1/watchlist/import``
to avoid replication loops.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.tickers import service as tickers_svc
from app.watchlist.models import WatchlistEntry

logger = logging.getLogger(__name__)


def _serialize(entry: WatchlistEntry, action: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"action": action, "symbol": entry.symbol}
    if action == "upsert":
        payload["notes"] = entry.notes
        payload["added_at"] = entry.added_at.isoformat() if entry.added_at else None
    return payload


async def _enqueue_replication(payload: dict[str, Any]) -> None:
    """Best-effort: log + swallow exceptions so replication never blocks CRUD."""
    try:
        from app.sync import service as sync_svc

        await sync_svc.enqueue_kind("watchlist", payload)
    except Exception:  # pragma: no cover - defensive
        logger.exception("watchlist: replication enqueue failed")


async def list_entries(*, limit: int = 200, offset: int = 0) -> List[WatchlistEntry]:
    async with _db.SessionLocal() as session:
        rows = await session.execute(
            select(WatchlistEntry)
            .order_by(WatchlistEntry.added_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all())


async def list_symbols() -> List[str]:
    """Hot path for the scheduler — just the symbols, ordered."""
    async with _db.SessionLocal() as session:
        rows = await session.execute(
            select(WatchlistEntry.symbol).order_by(WatchlistEntry.symbol)
        )
        return [r[0] for r in rows.all()]


async def get_entry(symbol: str) -> Optional[WatchlistEntry]:
    sym = tickers_svc.normalize(symbol)
    async with _db.SessionLocal() as session:
        return await session.get(WatchlistEntry, sym)


async def add_entry(symbol: str, notes: Optional[str] = None) -> WatchlistEntry:
    sym = tickers_svc.normalize(symbol)
    async with _db.SessionLocal() as session:
        # Ensure ticker registry has the symbol; watchlist FK requires it.
        await tickers_svc.upsert_ticker(session, sym, source="watchlist")

        existing = await session.get(WatchlistEntry, sym)
        if existing is not None:
            if notes is not None:
                existing.notes = notes
                await session.commit()
                await session.refresh(existing)
            await _enqueue_replication(_serialize(existing, "upsert"))
            return existing

        entry = WatchlistEntry(symbol=sym, notes=notes)
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
    await _enqueue_replication(_serialize(entry, "upsert"))
    return entry


async def update_entry(symbol: str, notes: Optional[str]) -> Optional[WatchlistEntry]:
    sym = tickers_svc.normalize(symbol)
    async with _db.SessionLocal() as session:
        entry = await session.get(WatchlistEntry, sym)
        if entry is None:
            return None
        entry.notes = notes
        await session.commit()
        await session.refresh(entry)
    await _enqueue_replication(_serialize(entry, "upsert"))
    return entry


async def remove_entry(symbol: str) -> bool:
    """Delete watchlist row only. Tickers/predictions/OHLCV stay."""
    sym = tickers_svc.normalize(symbol)
    async with _db.SessionLocal() as session:
        entry = await session.get(WatchlistEntry, sym)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
    await _enqueue_replication({"action": "delete", "symbol": sym})
    return True


# ----------------------------------------------------------------------
# Import path (called from /v1/watchlist/import receiver). Skips
# replication enqueue to avoid loops.
# ----------------------------------------------------------------------

async def apply_imported_change(payload: dict[str, Any]) -> str:
    """Apply a peer-pushed watchlist change. Returns 'upsert' | 'delete' | 'noop'."""
    action = payload.get("action")
    symbol = payload.get("symbol")
    if not action or not symbol:
        return "noop"
    sym = tickers_svc.normalize(symbol)

    async with _db.SessionLocal() as session:
        if action == "delete":
            entry = await session.get(WatchlistEntry, sym)
            if entry is None:
                return "noop"
            await session.delete(entry)
            await session.commit()
            return "delete"

        if action == "upsert":
            await tickers_svc.upsert_ticker(session, sym, source="watchlist")
            entry = await session.get(WatchlistEntry, sym)
            notes = payload.get("notes")
            if entry is None:
                entry = WatchlistEntry(symbol=sym, notes=notes)
                session.add(entry)
            else:
                entry.notes = notes
            await session.commit()
            return "upsert"

    return "noop"


async def bulk_add(symbols: Iterable[str]) -> int:
    """Add many symbols. Returns count newly added (existing ones skipped)."""
    added = 0
    for s in symbols:
        sym = tickers_svc.normalize(s)
        if not sym:
            continue
        existing = await get_entry(sym)
        if existing is None:
            await add_entry(sym)
            added += 1
    return added
