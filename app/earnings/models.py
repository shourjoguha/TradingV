"""ORM model for earnings_calendar."""
from __future__ import annotations

import datetime

from sqlalchemy import Date, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EarningsCalendarRow(Base):
    """One row per ticker in the rolling earnings universe.

    ``expected_at`` is the announced or estimated earnings date.
    ``confirmed_at`` is set when an 8-K Item 2.02 filing lands, indicating
    the release actually happened.
    ``last_universe_at`` is bumped on every refresh tick that includes
    this ticker — used for the 90-day TTL purge.
    """

    __tablename__ = "earnings_calendar"

    ticker: Mapped[str] = mapped_column(String(50), primary_key=True)
    expected_at: Mapped[datetime.date | None] = mapped_column(Date(), nullable=True)
    confirmed_at: Mapped[datetime.date | None] = mapped_column(Date(), nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fetched_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_universe_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_earnings_calendar_expected_at", "expected_at"),
    )
