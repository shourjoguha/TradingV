"""Derived market metrics — IV percentile, earnings dates. Phase 6.

A daily background job pulls these per watchlist ticker. Stored in the
``ticker_market_data`` table. No UI yet (per roadmap: "data accumulating,
ready for the future options chapter").

Provider: yfinance for v1 (free, has options chains + earnings calendar).
Compute IV percentile by sampling 1y of historical IV from atm options
chain. Best-effort; rows with errors store ``error`` text and partial data.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core import db as _db
from app.core.db import Base

logger = logging.getLogger(__name__)

_DEFAULT_TICK_SECONDS = 24 * 60 * 60  # daily


class TickerMarketData(Base):
    __tablename__ = "ticker_market_data"

    symbol: Mapped[str] = mapped_column(
        String(50), ForeignKey("tickers.symbol", ondelete="CASCADE"), primary_key=True
    )
    iv_30d: Mapped[float | None] = mapped_column(Float(), nullable=True)
    iv_percentile_1y: Mapped[float | None] = mapped_column(Float(), nullable=True)
    next_earnings_date: Mapped[datetime.date | None] = mapped_column(Date(), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    error: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (Index("ix_tmd_iv_percentile", "iv_percentile_1y"),)


async def _fetch_yfinance(symbol: str) -> dict:
    """Run yfinance in a thread (sync API). Returns partial data on error.

    Catches all exceptions — yfinance is flaky and we never want this to
    crash the daily loop.
    """
    def _sync() -> dict:
        try:
            import yfinance as yf  # type: ignore
        except ImportError as e:
            return {"error": f"yfinance not installed: {e}"}

        try:
            t = yf.Ticker(symbol)
        except Exception as e:  # noqa: BLE001
            return {"error": f"yf.Ticker failed: {e}"}

        out: dict = {"source": "yfinance", "iv_30d": None, "iv_percentile_1y": None, "next_earnings_date": None}

        # Earnings date — best effort.
        try:
            cal = t.calendar
            # yfinance returns DataFrame or dict depending on version; coerce.
            if cal is not None:
                ed = None
                if hasattr(cal, "loc"):
                    ed = cal.loc.get("Earnings Date") if hasattr(cal, "loc") else None
                elif isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                if ed is not None:
                    if hasattr(ed, "iloc"):
                        ed = ed.iloc[0]
                    if isinstance(ed, list) and ed:
                        ed = ed[0]
                    if isinstance(ed, datetime.date):
                        out["next_earnings_date"] = ed
                    elif hasattr(ed, "date"):
                        out["next_earnings_date"] = ed.date()
        except Exception as e:  # noqa: BLE001
            logger.debug("yfinance earnings fetch failed for %s: %s", symbol, e)

        # IV proxy: pick first option expiration ~30d out, take ATM call IV.
        # IV percentile 1y: skipped here (would need historical options data
        # that yfinance doesn't expose). Set to None; populate later when we
        # add a real options provider.
        try:
            expirations = list(t.options or [])
            if expirations:
                target = datetime.date.today() + datetime.timedelta(days=30)
                pick = min(
                    expirations,
                    key=lambda e: abs((datetime.date.fromisoformat(e) - target).days),
                )
                chain = t.option_chain(pick)
                spot = float(t.history(period="1d").iloc[-1]["Close"])
                calls = chain.calls
                if not calls.empty:
                    atm = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]
                    iv = float(atm["impliedVolatility"].iloc[0])
                    if iv > 0:
                        out["iv_30d"] = iv
        except Exception as e:  # noqa: BLE001
            logger.debug("yfinance IV fetch failed for %s: %s", symbol, e)

        return out

    return await asyncio.to_thread(_sync)


async def refresh_one(symbol: str) -> dict:
    """Fetch + upsert metrics for one ticker. Returns the stored row dict."""
    data = await _fetch_yfinance(symbol.upper())
    now = datetime.datetime.now(datetime.timezone.utc)
    error = data.get("error")
    async with _db.SessionLocal() as session:
        existing = await session.get(TickerMarketData, symbol.upper())
        if existing is None:
            row = TickerMarketData(
                symbol=symbol.upper(),
                iv_30d=data.get("iv_30d"),
                iv_percentile_1y=data.get("iv_percentile_1y"),
                next_earnings_date=data.get("next_earnings_date"),
                source=data.get("source"),
                fetched_at=now,
                error=error,
            )
            session.add(row)
        else:
            existing.iv_30d = data.get("iv_30d")
            existing.iv_percentile_1y = data.get("iv_percentile_1y")
            existing.next_earnings_date = data.get("next_earnings_date")
            existing.source = data.get("source") or existing.source
            existing.fetched_at = now
            existing.error = error
            row = existing
        await session.commit()
        return {
            "symbol": row.symbol,
            "iv_30d": row.iv_30d,
            "iv_percentile_1y": row.iv_percentile_1y,
            "next_earnings_date": (
                row.next_earnings_date.isoformat() if row.next_earnings_date else None
            ),
            "fetched_at": row.fetched_at.isoformat(),
            "error": row.error,
        }


async def refresh_watchlist() -> dict[str, int]:
    """Refresh metrics for every active watchlist symbol. Returns stats."""
    from app.watchlist.models import WatchlistEntry

    stats = {"scanned": 0, "ok": 0, "failed": 0}
    async with _db.SessionLocal() as session:
        from sqlalchemy import select as _select

        rows = (await session.execute(_select(WatchlistEntry.symbol))).scalars().all()

    stats["scanned"] = len(rows)
    for sym in rows:
        try:
            r = await refresh_one(sym)
            if r.get("error"):
                stats["failed"] += 1
            else:
                stats["ok"] += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("refresh_one(%s) crashed: %s", sym, e)
            stats["failed"] += 1
    return stats


async def market_data_loop(
    *, tick_seconds: int = _DEFAULT_TICK_SECONDS, stop_event: Optional[asyncio.Event] = None
) -> None:
    """Daily refresh loop. Idempotent; safe to interrupt."""
    logger.info("market_data.loop started (tick=%ss)", tick_seconds)
    while True:
        try:
            stats = await refresh_watchlist()
            logger.info(
                "market_data.refresh: scanned=%d ok=%d failed=%d",
                stats["scanned"],
                stats["ok"],
                stats["failed"],
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("market_data.refresh tick failed: %s", e)

        try:
            if stop_event is not None:
                await asyncio.wait_for(stop_event.wait(), timeout=tick_seconds)
                if stop_event.is_set():
                    logger.info("market_data.loop stopping (signal)")
                    return
            else:
                await asyncio.sleep(tick_seconds)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise
