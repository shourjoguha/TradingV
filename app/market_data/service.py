from __future__ import annotations

import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.market_data import registry
from app.market_data.intervals import is_canonical
from app.market_data.models import OhlcvBar
from app.market_data.providers.base import Bar, UnsupportedRequest
from app.tickers import service as tickers_svc


def normalize(symbol: str) -> str:
    return symbol.strip().upper()


async def _upsert_bars(
    session: AsyncSession,
    symbol: str,
    interval: str,
    provider_name: str,
    bars: List[Bar],
) -> int:
    if not bars:
        return 0

    rows = [
        {
            "symbol": symbol,
            "interval": interval,
            "ts": b.ts,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "amount": b.amount,
            "provider": provider_name,
        }
        for b in bars
    ]

    dialect = session.bind.dialect.name if session.bind else ""
    if dialect == "postgresql":
        stmt = pg_insert(OhlcvBar).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[OhlcvBar.symbol, OhlcvBar.interval, OhlcvBar.ts],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "amount": stmt.excluded.amount,
                "provider": stmt.excluded.provider,
            },
        )
    elif dialect == "sqlite":
        stmt = sqlite_insert(OhlcvBar).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[OhlcvBar.symbol, OhlcvBar.interval, OhlcvBar.ts],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "amount": stmt.excluded.amount,
                "provider": stmt.excluded.provider,
            },
        )
    else:
        # Fallback: delete-then-insert per PK. Should not happen in supported envs.
        for r in rows:
            existing = await session.get(
                OhlcvBar, (r["symbol"], r["interval"], r["ts"])
            )
            if existing is not None:
                await session.delete(existing)
        await session.flush()
        session.add_all([OhlcvBar(**r) for r in rows])
        return len(rows)

    await session.execute(stmt)
    return len(rows)


async def refresh(
    symbol: str,
    interval: str,
    *,
    asset_class: Optional[str] = None,
    start: Optional[datetime.datetime] = None,
    end: Optional[datetime.datetime] = None,
) -> int:
    """Fetch from provider and upsert into cache. Returns number of bars touched."""
    if not is_canonical(interval):
        raise UnsupportedRequest(asset_class=asset_class or "unknown", interval=interval)

    sym = normalize(symbol)

    # Resolve asset class — prefer registry, else infer.
    async with _db.SessionLocal() as session:
        t = await tickers_svc.get_ticker(session, sym)
        if t is None:
            # Auto-register so the symbol shows up in the dropdown.
            t = await tickers_svc.upsert_ticker(
                session, sym, source="analysis", asset_class=asset_class
            )
            await session.commit()
        resolved_asset_class = asset_class or t.asset_class

    provider = registry.resolve(resolved_asset_class, interval)
    bars = await provider.fetch_ohlcv(sym, resolved_asset_class, interval, start, end)

    async with _db.SessionLocal() as session:
        count = await _upsert_bars(session, sym, interval, provider.name, bars)
        await session.commit()
    return count


async def get_cached(
    symbol: str,
    interval: str,
    *,
    limit: int = 500,
    start: Optional[datetime.datetime] = None,
    end: Optional[datetime.datetime] = None,
) -> List[OhlcvBar]:
    sym = normalize(symbol)
    stmt = select(OhlcvBar).where(
        OhlcvBar.symbol == sym, OhlcvBar.interval == interval
    )
    if start is not None:
        stmt = stmt.where(OhlcvBar.ts >= start)
    if end is not None:
        stmt = stmt.where(OhlcvBar.ts <= end)
    # Take the most recent N by descending then reverse for chronological output.
    stmt = stmt.order_by(OhlcvBar.ts.desc()).limit(limit)

    async with _db.SessionLocal() as session:
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def count_cached(symbol: str, interval: str) -> int:
    from sqlalchemy import func as sqlfunc

    sym = normalize(symbol)
    async with _db.SessionLocal() as session:
        result = await session.execute(
            select(sqlfunc.count()).select_from(OhlcvBar).where(
                OhlcvBar.symbol == sym, OhlcvBar.interval == interval
            )
        )
        return int(result.scalar_one())
