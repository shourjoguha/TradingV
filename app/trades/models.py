"""Trades — Phase 5 trade journal.

Manual entry. Brokerage-API integration is intentionally out of scope: a
single-user manual journal is enough to close the prediction → trade →
outcome loop, and saves a giant integration surface.

Optional FK to ``opportunities`` enables per-rule P&L attribution: "if I'd
taken every R1 BUY signal, what's my P&L?"
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        nullable=True,
    )
    # rx v1.x.1-a: nullable FK to recommendations(id). Populated by the
    # trade-capture form when the operator marks a trade as prompted by a
    # specific rec. Powers the `position_thesis_match` signal in Phase B.
    # ON DELETE SET NULL so trades survive a rec purge.
    related_rec_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # retrieval-depth Phase 4 (B4 attribution split): did the linked rec
    # PREDICT this trade (operator decided independently) or CAUSE it?
    # 'influenced' trades are excluded from predictive-lift so a rec can't
    # earn credit for a move it caused. NULL = unclassified/legacy.
    rec_influence_kind: Mapped[str | None] = mapped_column(
        String(24), nullable=True
    )
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # 'buy' | 'sell'
    qty: Mapped[float] = mapped_column(Float(), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float(), nullable=False)
    entry_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    exit_price: Mapped[float | None] = mapped_column(Float(), nullable=True)
    exit_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    realized_pnl: Mapped[float | None] = mapped_column(Float(), nullable=True)
    fees: Mapped[float] = mapped_column(Float(), nullable=False, server_default="0")
    notes_md: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # Phase 5 (tv_context enrichment): list of tv_context_item ids attributed
    # to this trade at close time. Lets the operator walk a past decision —
    # "what TV signals fed into this trade?"
    context_refs: Mapped[list] = mapped_column(
        JSON(), nullable=False, server_default="[]"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_trades_ticker", "ticker"),
        Index("ix_trades_entry_at", "entry_at"),
        Index("ix_trades_opportunity", "opportunity_id"),
        CheckConstraint(
            "rec_influence_kind IS NULL OR "
            "rec_influence_kind IN ('preceded_independent','influenced')",
            name="ck_trades_rec_influence_kind",
        ),
    )
