"""agent_decisions table — the Agents lane's own storage.

Deliberately separate from Kronos' ``prediction_points`` / ``opportunities``:
this engine runs side-by-side and writes only here. Surfacing a decision into
the shared ``opportunities`` feed is optional and gated (see
``app/agents/service.py`` + ``AGENTS_EMIT_OPPORTUNITIES``).

Idempotency: ``UNIQUE(ticker, made_on, engine_version)`` — re-running the daily
loop for a ticker on the same day is a no-op rather than a duplicate row.
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AgentDecisionRow(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    made_on: Mapped[datetime.date] = mapped_column(Date(), nullable=False)

    engine: Mapped[str] = mapped_column(String(64), nullable=False, server_default="tradingagents")
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)

    stance: Mapped[str] = mapped_column(String(8), nullable=False)  # BUY | SELL | HOLD
    confidence: Mapped[float | None] = mapped_column(Float(), nullable=True)
    rationale_md: Mapped[str | None] = mapped_column(Text(), nullable=True)
    transcript_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON(), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "ticker", "made_on", "engine_version", name="uq_agent_decision_ticker_day"
        ),
        Index("ix_agent_decisions_ticker", "ticker"),
        Index("ix_agent_decisions_made_on", "made_on"),
    )
