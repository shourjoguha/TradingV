"""Watchlist service.

Auto-upserts the symbol into the ``tickers`` registry on add (so a brand-new
ticker can be added to the watchlist without separate POST /v1/tickers).
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.tickers import service as tickers_svc
from app.watchlist.models import WatchlistEntry


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
            return existing

        entry = WatchlistEntry(symbol=sym, notes=notes)
        session.add(entry)
        await session.commit()
        return entry


async def update_entry(symbol: str, notes: Optional[str]) -> Optional[WatchlistEntry]:
    sym = tickers_svc.normalize(symbol)
    async with _db.SessionLocal() as session:
        entry = await session.get(WatchlistEntry, sym)
        if entry is None:
            return None
        entry.notes = notes
        await session.commit()
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
        return True


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
