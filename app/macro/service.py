"""Macro Workbench service — Phase M-1.

Single writer for ``macro_series``. Refresh per symbol, batch via
``refresh_all``. Read paths: ``get_series`` (single symbol) and
``compute_ratio`` (numerator/denominator inner-joined on date).

Ratios are NOT materialised — computed on demand. Reconsider only if
profile shows the join hurts; with ~30 symbols × 5y of daily rows
(~55k rows) it's a rounding error.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.core import db as _db
from app.macro.models import MacroSeries
from app.macro.providers.fred_provider import FREDProvider
from app.macro.providers.yfinance_provider import YFinanceMacroProvider
from app.macro.registry import RegistryEntry, load_registry, lookup_source

logger = logging.getLogger(__name__)

# Default zoom on read. Five years of daily data = roughly the smallest
# window a long-horizon hypothesis cares about.
_DEFAULT_SINCE_YEARS = 5

# Daily ingestion tick.
_DEFAULT_TICK_SECONDS = 24 * 60 * 60


# ----------------------------------------------------------------------
# Provider routing
# ----------------------------------------------------------------------

_yf = YFinanceMacroProvider()
_fred = FREDProvider()


def _provider_for(source: str):
    if source == "yfinance":
        return _yf
    if source == "fred":
        return _fred
    raise ValueError(f"unknown source '{source}'")


# ----------------------------------------------------------------------
# Upsert — dialect-aware so SQLite (tests) and Postgres (prod) both work.
# ----------------------------------------------------------------------


# Postgres caps a single bind list at 32767 parameters. Each row uses 5
# columns (id, symbol, source, ts, value), so 6000 rows × 5 = 30000 params
# stays comfortably under the limit. yfinance can return >10k daily bars
# for old tickers; without chunking the upsert blows up live.
_UPSERT_CHUNK_ROWS = 1000


async def _upsert_points(
    *, symbol: str, source: str, points: List[tuple]
) -> int:
    if not points:
        return 0
    rows = [
        {
            "symbol": symbol,
            "source": source,
            "ts": ts,
            "value": float(value),
        }
        for ts, value in points
    ]

    async with _db.SessionLocal() as session:
        bind = session.get_bind()
        dialect = bind.dialect.name if hasattr(bind, "dialect") else "postgresql"

        # Chunk to stay under Postgres' 32767-parameter limit. SQLite's
        # default limit is 999 in older builds and 32766 in modern ones —
        # the same chunk size is safe everywhere.
        for i in range(0, len(rows), _UPSERT_CHUNK_ROWS):
            chunk = rows[i : i + _UPSERT_CHUNK_ROWS]
            if dialect == "sqlite":
                stmt = sqlite_insert(MacroSeries).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "ts"],
                    set_={"value": stmt.excluded.value},
                )
            else:
                stmt = pg_insert(MacroSeries).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "ts"],
                    set_={
                        "value": stmt.excluded.value,
                        "source": stmt.excluded.source,
                    },
                )
            try:
                await session.execute(stmt)
            except IntegrityError as e:
                await session.rollback()
                logger.warning(
                    "macro upsert IntegrityError for %s chunk %d: %s",
                    symbol,
                    i // _UPSERT_CHUNK_ROWS,
                    e,
                )
                return 0
        await session.commit()

    return len(rows)


# ----------------------------------------------------------------------
# Refresh — per symbol + bulk
# ----------------------------------------------------------------------


async def refresh(
    symbol: str,
    *,
    source: Optional[str] = None,
    since: Optional[datetime.date] = None,
) -> int:
    """Fetch from upstream + upsert. Returns rows touched.

    ``source`` auto-resolved from registry if unset. Raises
    ``ValueError`` for an unknown symbol so callers (route) can return
    400 instead of silently noop'ing.
    """
    resolved_source = source or lookup_source(symbol)
    if resolved_source is None:
        raise ValueError(
            f"symbol '{symbol}' not in macro registry; add to "
            "app/macro/registry.yaml first"
        )
    provider = _provider_for(resolved_source)
    points = await provider.fetch(symbol, since)
    return await _upsert_points(symbol=symbol, source=resolved_source, points=points)


async def refresh_all() -> Dict[str, Any]:
    """Walk the registry and refresh every symbol. Per-symbol try/except
    so one upstream hiccup doesn't poison the whole tick.
    """
    stats: Dict[str, Any] = {
        "rows_touched": 0,
        "ok": 0,
        "failed": 0,
        "skipped": 0,
        "failures": [],
    }
    for entry in load_registry():
        try:
            n = await refresh(entry.symbol, source=entry.source)
            stats["rows_touched"] += n
            if n == 0:
                stats["skipped"] += 1
            else:
                stats["ok"] += 1
        except Exception as e:  # noqa: BLE001
            stats["failed"] += 1
            stats["failures"].append(f"{entry.symbol}: {type(e).__name__}: {e}")
            logger.warning(
                "macro refresh failed for %s/%s: %s",
                entry.symbol,
                entry.source,
                e,
            )
    return stats


# ----------------------------------------------------------------------
# Read paths
# ----------------------------------------------------------------------


def _default_since() -> datetime.date:
    today = datetime.date.today()
    try:
        return today.replace(year=today.year - _DEFAULT_SINCE_YEARS)
    except ValueError:
        # Feb 29 → Feb 28
        return today.replace(year=today.year - _DEFAULT_SINCE_YEARS, day=28)


async def get_series(
    symbol: str,
    *,
    since: Optional[datetime.date] = None,
    until: Optional[datetime.date] = None,
) -> List[Dict[str, Any]]:
    """Cached values for one symbol. Default ``since`` = 5 years ago."""
    since = since or _default_since()
    async with _db.SessionLocal() as session:
        stmt = (
            select(MacroSeries.ts, MacroSeries.value)
            .where(MacroSeries.symbol == symbol)
            .where(MacroSeries.ts >= since)
        )
        if until is not None:
            stmt = stmt.where(MacroSeries.ts <= until)
        stmt = stmt.order_by(MacroSeries.ts.asc())
        rows = (await session.execute(stmt)).all()
    return [{"ts": ts, "value": float(value)} for ts, value in rows]


async def compute_ratio(
    *,
    numerator: str,
    denominator: str,
    since: Optional[datetime.date] = None,
    until: Optional[datetime.date] = None,
) -> List[Dict[str, Any]]:
    """Inner-join num + denom on date; emit (ts, num/denom) pairs.

    Skips dates where:
    - Either side is missing.
    - Denominator is zero (avoids inf / NaN propagating to clients).
    """
    since = since or _default_since()

    # Two simple selects then join in Python — keeps the SQL trivial and
    # works identically on SQLite (tests) + Postgres (prod). At ~5y/daily
    # × ~30 symbols this is sub-millisecond.
    async with _db.SessionLocal() as session:
        num_stmt = (
            select(MacroSeries.ts, MacroSeries.value)
            .where(MacroSeries.symbol == numerator)
            .where(MacroSeries.ts >= since)
        )
        den_stmt = (
            select(MacroSeries.ts, MacroSeries.value)
            .where(MacroSeries.symbol == denominator)
            .where(MacroSeries.ts >= since)
        )
        if until is not None:
            num_stmt = num_stmt.where(MacroSeries.ts <= until)
            den_stmt = den_stmt.where(MacroSeries.ts <= until)
        num_rows = (await session.execute(num_stmt)).all()
        den_rows = (await session.execute(den_stmt)).all()

    den_map = {ts: float(v) for ts, v in den_rows}
    out: List[Dict[str, Any]] = []
    for ts, num_v in num_rows:
        d = den_map.get(ts)
        if d is None or d == 0.0:
            continue
        out.append({"ts": ts, "value": float(num_v) / d})
    out.sort(key=lambda p: p["ts"])
    return out


# ----------------------------------------------------------------------
# Lifespan ingestion loop
# ----------------------------------------------------------------------


async def ingestion_loop(
    *,
    tick_seconds: int = _DEFAULT_TICK_SECONDS,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Long-lived lifespan task. Refreshes the full registry once at
    startup (catch-up) then every ``tick_seconds``. Cancellation-safe.
    """
    logger.info("macro.ingestion_loop started (tick=%ss)", tick_seconds)
    first = True
    while True:
        try:
            stats = await refresh_all()
            logger.info(
                "macro.ingestion: rows_touched=%d ok=%d failed=%d skipped=%d%s",
                stats["rows_touched"],
                stats["ok"],
                stats["failed"],
                stats["skipped"],
                " (first tick)" if first else "",
            )
            first = False
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("macro.ingestion tick failed: %s", e)

        try:
            if stop_event is not None:
                await asyncio.wait_for(stop_event.wait(), timeout=tick_seconds)
                if stop_event.is_set():
                    logger.info("macro.ingestion_loop stopping (signal)")
                    return
            else:
                await asyncio.sleep(tick_seconds)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise
