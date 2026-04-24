"""Outbound ticker sync queue.

Each row represents one (symbol, asset_class) that needs to be pushed to
the peer backend. Rows drain FIFO via `drain_outbox`. Idempotent on the
receiver side — safe to retry.
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    peer_url: Mapped[str] = mapped_column(String(256), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
