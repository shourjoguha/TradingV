"""Flat prediction storage — one row per (task, target bar).

Why a flat table when ``analysis_tasks.result_json`` already holds the
forecast list?
- Comparison queries need ``GROUP BY target_date`` and ``ORDER BY made_on``,
  which are awkward on JSON.
- Day-of-week filtering needs an indexable scalar column.
- The flat shape lets receivers index by ``(ticker, target_date)`` so
  cross-run comparisons (k-days-ago vs actual) are O(small).

The JSON in ``result_json`` is still authoritative — this table is a
materialised view of it. Backfill regenerates it on demand.
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class PredictionPoint(Base):
    __tablename__ = "prediction_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)

    # The UTC date on which the forecast was generated.
    made_on: Mapped[datetime.date] = mapped_column(Date(), nullable=False)
    # Python weekday(): Mon=0..Sun=6. Indexed for ``?made_on_dow=`` filter.
    made_on_dow: Mapped[int] = mapped_column(SmallInteger(), nullable=False)

    # The bar this row predicts.
    target_date: Mapped[datetime.date] = mapped_column(Date(), nullable=False)
    target_ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Forecast offset: 1 = "first bar after made_on", 2 = "second", etc.
    horizon_offset: Mapped[int] = mapped_column(SmallInteger(), nullable=False)

    # Forecast values. Volume + amount may be 0/None for non-volume models.
    open: Mapped[float] = mapped_column(Float(), nullable=False)
    high: Mapped[float] = mapped_column(Float(), nullable=False)
    low: Mapped[float] = mapped_column(Float(), nullable=False)
    close: Mapped[float] = mapped_column(Float(), nullable=False)
    volume: Mapped[float | None] = mapped_column(Float(), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float(), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Drill down "what did we predict for target X across all runs?"
        Index("ix_pp_target_ticker", "target_date", "ticker"),
        # Drill down "all forecasts made on day Y"
        Index("ix_pp_made_on_ticker", "made_on", "ticker"),
        # Compound for the "predictions made k-days-ago vs actual" query
        Index("ix_pp_ticker_target_made", "ticker", "target_date", "made_on"),
        # Day-of-week filter
        Index("ix_pp_made_on_dow", "made_on_dow"),
    )
