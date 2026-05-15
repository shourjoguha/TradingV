"""ORM model for the ticker_review_queue table (Phase D)."""
from __future__ import annotations

import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TickerReviewEntry(Base):
    __tablename__ = "ticker_review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    times_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    channels: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    recent_video_ids: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    recent_caption_snippets: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending"
    )
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_target: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    previously_dismissed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("ticker", name="uq_ticker_review_queue_ticker"),
        Index(
            "ix_ticker_review_queue_status_last_seen",
            "status",
            "last_seen_at",
        ),
    )
