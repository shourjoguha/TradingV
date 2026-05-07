"""ORM models for TradingView-context items + hypothesis-link sibling table."""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


KIND_WEBHOOK = "webhook"
KIND_SCREENSHOT = "screenshot"
KIND_NOTE = "note"
KIND_IDEA = "idea"
KIND_EVENT = "event"
ALL_KINDS = (KIND_WEBHOOK, KIND_SCREENSHOT, KIND_NOTE, KIND_IDEA, KIND_EVENT)

STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"
STATUS_ARCHIVED = "archived"
ALL_STATUSES = (STATUS_ACTIVE, STATUS_EXPIRED, STATUS_ARCHIVED)


class TVContextItem(Base):
    __tablename__ = "tv_context_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="tradingview"
    )
    captured_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=STATUS_ACTIVE
    )
    payload: Mapped[dict] = mapped_column(JSON(), nullable=False)
    tombstone: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    vault_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    heavy_blob_dropped: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, server_default="0"
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            f"kind IN ({','.join(repr(k) for k in ALL_KINDS)})",
            name="ck_tv_context_items_kind",
        ),
        CheckConstraint(
            f"status IN ({','.join(repr(s) for s in ALL_STATUSES)})",
            name="ck_tv_context_items_status",
        ),
        Index("ix_tv_context_items_ticker_captured", "ticker", "captured_at"),
        Index("ix_tv_context_items_status_expires", "status", "expires_at"),
        Index("ix_tv_context_items_kind_ticker", "kind", "ticker"),
        Index("ix_tv_context_items_dedupe", "dedupe_key", "captured_at"),
    )


VALID_STANCES = ("supports", "challenges", "context")


class HypothesisTVContextLink(Base):
    """Pointer from a hypothesis to a tv_context_item.

    Sibling to ``hypothesis_node_links`` (vault-path links). Kept separate
    so neither table needs a nullable composite-PK column.
    """

    __tablename__ = "hypothesis_tv_context_links"

    hypothesis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hypothesis.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tv_context_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tv_context_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    stance: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="context"
    )
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    added_by: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="operator"
    )

    __table_args__ = (
        CheckConstraint(
            f"stance IN ({','.join(repr(s) for s in VALID_STANCES)})",
            name="ck_hyp_tv_ctx_stance",
        ),
        Index("ix_hyp_tv_ctx_links_item", "tv_context_item_id"),
    )
