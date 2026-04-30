"""Macro time-series ORM model — Phase M-1.

One row per ``(symbol, ts)``. Symbols are strings (no foreign-key registry)
so adding a hypothesis-specific symbol is one YAML edit + one refresh, not
a migration.
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MacroSeries(Base):
    __tablename__ = "macro_series"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    ts: Mapped[datetime.date] = mapped_column(Date(), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("symbol", "ts", name="uq_macro_series_symbol_ts"),
        CheckConstraint(
            "source IN ('yfinance', 'fred', 'manual')",
            name="ck_macro_series_source",
        ),
        Index("ix_macro_series_symbol_ts", "symbol", "ts"),
    )
