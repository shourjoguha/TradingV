"""Watchlist — the actively-tracked subset of tickers.

Distinct from ``tickers`` (the global symbol registry, which holds
everything we've ever seen, including transient TradingView-alert symbols).
The watchlist is the set the daily scheduled forecast runner will iterate.

v1: single global watchlist (one row per tracked symbol). Adding a
``watchlist_id`` column later for multi-watchlist support is trivial.

Removal semantics: deleting a row STOPS future scheduled runs but
leaves all collected data (``analysis_*``, ``ohlcv_bars``,
``prediction_points``) untouched.
"""
from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WatchlistEntry(Base):
    __tablename__ = "watchlist"

    symbol: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tickers.symbol", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
