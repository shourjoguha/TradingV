"""Per-prediction accuracy storage — Phase 1.1 trust through feedback.

One row per evaluated ``prediction_points`` row. Stores per-row error so
aggregate metrics (MAPE, RMSE, directional hit-rate) are computed at query
time over flexible windows ``(ticker, horizon, model, date_range)``.

Why per-row, not pre-aggregated:
- Aggregations need to slide over time and re-window per UI choice
  (last 30, last quarter, etc.). Pre-aggregating locks the window.
- Drift detection compares recent vs all-time — cheaper if rows are raw.
- Storage is cheap; one row per (prediction, evaluation) is fine.

The ``UNIQUE`` constraint on ``prediction_id`` enforces idempotency: the
evaluator can re-run safely; nothing gets double-counted.
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class PredictionAccuracy(Base):
    __tablename__ = "prediction_accuracy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    prediction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prediction_points.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)
    horizon_offset: Mapped[int] = mapped_column(SmallInteger(), nullable=False)
    made_on: Mapped[datetime.date] = mapped_column(Date(), nullable=False)
    target_date: Mapped[datetime.date] = mapped_column(Date(), nullable=False)

    predicted_close: Mapped[float] = mapped_column(Float(), nullable=False)
    actual_close: Mapped[float] = mapped_column(Float(), nullable=False)
    # Close at made_on (T0). Used for direction-correctness vs prediction.
    # Nullable when the made_on bar is missing from ohlcv_bars.
    baseline_close: Mapped[float | None] = mapped_column(Float(), nullable=True)

    # Signed: (actual - predicted) / actual. Positive = predicted under target.
    error_pct: Mapped[float] = mapped_column(Float(), nullable=False)
    # |error_pct|. Aggregated as MAPE.
    abs_error_pct: Mapped[float] = mapped_column(Float(), nullable=False)
    # (actual - predicted)^2. Aggregated as MSE → sqrt = RMSE.
    squared_error: Mapped[float] = mapped_column(Float(), nullable=False)

    # sign(predicted - baseline) == sign(actual - baseline). Null if baseline missing.
    direction_correct: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)

    evaluated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_pa_ticker_horizon", "ticker", "horizon_offset"),
        Index("ix_pa_evaluated_at", "evaluated_at"),
        Index("ix_pa_ticker_evaluated", "ticker", "evaluated_at"),
    )


class DriftAlert(Base):
    """Open drift flag for a (ticker, horizon, model) pair.

    Created by ``accuracy.drift.detect_drift`` when recent MAPE > all-time
    MAPE × ``DRIFT_RATIO_THRESHOLD`` (with min sample sizes). Idempotent:
    while an open alert exists for a pair, ``detect_drift`` won't create a
    duplicate. Acknowledging via ``POST /v1/accuracy/drift/{id}/ack`` sets
    ``acknowledged_at`` and clears the way for a future re-flag.
    """

    __tablename__ = "drift_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    horizon_offset: Mapped[int] = mapped_column(SmallInteger(), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recent_mape: Mapped[float] = mapped_column(Float(), nullable=False)
    all_time_mape: Mapped[float] = mapped_column(Float(), nullable=False)
    ratio: Mapped[float] = mapped_column(Float(), nullable=False)
    recent_sample_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    all_time_sample_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    flagged_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_drift_open", "acknowledged_at", "ticker"),
        Index("ix_drift_ticker_horizon", "ticker", "horizon_offset"),
    )
