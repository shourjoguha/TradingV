"""Ticker labels — free-form EAV metadata.

Each row pins one (symbol, key) → JSON value. The JSON column lets a
single table store strings, booleans, lists, dicts — anything pyJSON
serialises — without per-key schema migrations.

Common keys (informal — NOT enforced):
- ``sector``           : str (e.g. "tech", "consumer-staples")
- ``capsize``          : str (one of "micro" | "small" | "mid" | "large")
- ``notes``            : str (free-form)
- ``insider_buy``      : bool
- ``hedge_funds``      : list[str]
- ``planned_horizon``  : str (e.g. "months" | "quarters" | "years")

But any user-defined key is accepted. Frontend can present a curated
dropdown for common ones while still allowing arbitrary additions.
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    JSON,
    DateTime,
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


class TickerLabel(Base):
    __tablename__ = "ticker_labels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    symbol: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tickers.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    # value can be any JSON: str/bool/int/float/list/dict.
    value: Mapped[object] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("symbol", "key", name="uq_ticker_labels_symbol_key"),
        Index("ix_ticker_labels_key", "key"),
    )
