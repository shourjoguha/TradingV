from __future__ import annotations

import datetime
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.tickers.asset_class import infer_asset_class
from app.tickers.models import Ticker


def normalize(symbol: str) -> str:
    return symbol.strip().upper()


async def upsert_ticker(
    session: AsyncSession,
    symbol: str,
    *,
    source: str,
    asset_class: Optional[str] = None,
    notes: Optional[str] = None,
) -> Ticker:
    """Insert new ticker or update last_seen on existing. Idempotent."""
    sym = normalize(symbol)
    if not sym:
        raise ValueError("symbol cannot be empty")

    existing = await session.get(Ticker, sym)
    if existing is not None:
        existing.last_seen = datetime.datetime.now(datetime.timezone.utc)
        if asset_class is not None:
            existing.asset_class = asset_class
        if notes is not None:
            existing.notes = notes
        return existing

    row = Ticker(
        symbol=sym,
        asset_class=asset_class or infer_asset_class(sym),
        source=source,
        notes=notes,
    )
    session.add(row)
    return row


async def upsert_many(
    session: AsyncSession,
    symbols: Iterable[str],
    *,
    source: str,
) -> List[Ticker]:
    out: List[Ticker] = []
    for s in symbols:
        if not s or not s.strip():
            continue
        out.append(await upsert_ticker(session, s, source=source))
    return out


async def list_tickers(
    session: AsyncSession,
    *,
    asset_class: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 500,
) -> List[Ticker]:
    stmt = select(Ticker)
    if asset_class:
        stmt = stmt.where(Ticker.asset_class == asset_class)
    if q:
        stmt = stmt.where(Ticker.symbol.ilike(f"%{normalize(q)}%"))
    stmt = stmt.order_by(Ticker.symbol).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_ticker(session: AsyncSession, symbol: str) -> Optional[Ticker]:
    return await session.get(Ticker, normalize(symbol))


async def patch_ticker(
    session: AsyncSession,
    symbol: str,
    *,
    asset_class: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[Ticker]:
    row = await get_ticker(session, symbol)
    if row is None:
        return None
    if asset_class is not None:
        row.asset_class = asset_class
    if notes is not None:
        row.notes = notes
    return row


# --- Session-managed convenience wrappers used by routes / webhook ---

async def upsert_from_webhook(symbol: str) -> None:
    async with _db.SessionLocal() as session:
        await upsert_ticker(session, symbol, source="alert")
        await session.commit()


async def backfill_from_alerts() -> int:
    """Populate tickers from distinct symbols in alerts. Idempotent.

    Returns number of rows inserted or touched.
    """
    from app.alerts.models import Alert

    async with _db.SessionLocal() as session:
        result = await session.execute(select(Alert.ticker).distinct())
        symbols = [row[0] for row in result.all() if row[0]]
        touched = await upsert_many(session, symbols, source="alert")
        await session.commit()
        return len(touched)
