"""Opportunities table — Phase 3.1 actionability bridge.

A signal that crossed a threshold rule. One row per (prediction, rule) —
``UNIQUE(source_prediction_id, rule_id)`` enforces idempotency so the
generator can be re-run without duplicates.

Lifecycle:
- ``open`` — generated, awaiting user action
- ``acted`` — user marked it acted (typically followed by a Trade row)
- ``dismissed`` — user explicitly skipped, with optional reason
- ``expired`` — past ``expires_at`` without action (sweeper sets this)
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # 'buy' | 'sell'

    generated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_prediction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prediction_points.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_model_id: Mapped[str] = mapped_column(String(64), nullable=False)

    rule_id: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_label: Mapped[str] = mapped_column(String(128), nullable=False)

    predicted_move_pct: Mapped[float] = mapped_column(Float(), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(), nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="open"
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dismissed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dismissed_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "source_prediction_id", "rule_id", name="uq_opp_prediction_rule"
        ),
        Index("ix_opp_status", "status"),
        Index("ix_opp_ticker_status", "ticker", "status"),
        Index("ix_opp_generated_at", "generated_at"),
    )
