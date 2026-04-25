"""Outbound sync queue.

A row represents one unit of work to push to the peer backend. Two kinds:
- ``ticker``: push a (symbol, asset_class) pair to peer ``POST /v1/tickers``.
- ``result``: push a full analysis job snapshot to peer ``POST /v1/analysis/import``.

Both kinds drain through the same ``drain_outbox`` loop, with the same
exponential-backoff retry policy. Receivers are idempotent.
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    peer_url: Mapped[str] = mapped_column(String(256), nullable=False)
    # 'ticker' (default — pre-existing rows) or 'result'.
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ticker", server_default="ticker"
    )
    # Populated for kind='ticker'. NULL for kind='result'.
    symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    asset_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Populated for kind='result' (full job snapshot). NULL for kind='ticker'.
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
