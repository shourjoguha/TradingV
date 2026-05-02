"""ResearchQuery — audit log of stress-test queries."""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DISMISSED = "dismissed"
STATUS_ERROR = "error"

ALL_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_DISMISSED, STATUS_ERROR)


class ResearchQuery(Base):
    __tablename__ = "research_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    query: Mapped[str] = mapped_column(Text(), nullable=False)
    hypothesis_ids: Mapped[list] = mapped_column(JSON(), nullable=False)
    answer_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verdict: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    est_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    bundle: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    response: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=STATUS_PENDING
    )
    approved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_action: Mapped[dict | None] = mapped_column(JSON(), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'dismissed', 'error')",
            name="ck_research_queries_status",
        ),
        Index("ix_research_queries_asked_at", "asked_at"),
    )
