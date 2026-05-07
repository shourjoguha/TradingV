"""ORM models for the hypothesis object + its evaluation log — M-2."""
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
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# Status enum-as-string so SQLite parity is free.
STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"
STATUS_INVALIDATED = "invalidated"
STATUS_CANCELLED = "cancelled"           # auto-cancel via precondition cascade
STATUS_MANUAL_CLOSED = "manual_closed"   # operator dismissal

ALL_STATUSES = (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_INVALIDATED,
    STATUS_CANCELLED,
    STATUS_MANUAL_CLOSED,
)

# Claim types — operator taxonomy. Drives default TTL via service.TTL_BY_CLAIM_TYPE.
CLAIM_REGIME = "regime"
CLAIM_TACTICAL = "tactical"
CLAIM_SINGLE_NAME = "single_name"
CLAIM_BREAKOUT = "breakout"

ALL_CLAIM_TYPES = (CLAIM_REGIME, CLAIM_TACTICAL, CLAIM_SINGLE_NAME, CLAIM_BREAKOUT)


class Hypothesis(Base):
    __tablename__ = "hypothesis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(32), nullable=False)
    axis: Mapped[str] = mapped_column(String(64), nullable=False)

    # Self-references. Sizing parent (optional) and existence precondition
    # (optional). Both ON DELETE SET NULL so deleting a parent doesn't
    # cascade-blow up its children — operator audits the orphans.
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("hypothesis.id", ondelete="SET NULL"),
        nullable=True,
    )
    precondition_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("hypothesis.id", ondelete="SET NULL"),
        nullable=True,
    )

    primary_metric: Mapped[str] = mapped_column(String(200), nullable=False)
    tracking_signal: Mapped[str] = mapped_column(String(200), nullable=False)

    # Invalidator DSL — see app.hypotheses.invalidator. Stored as JSON for
    # SQLite/Postgres parity (Postgres can index JSONB later if needed).
    invalidator: Mapped[dict] = mapped_column(JSON(), nullable=False)

    ttl_months: Mapped[int] = mapped_column(Integer(), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=STATUS_ACTIVE
    )
    body_md: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # Phase 4 (TV-context gating): when TRUE, /v1/research/ask short-circuits
    # to status='needs_context' if any operator-supplied ticker has zero
    # recent tv_context items. See app.research.service._check_tv_context.
    requires_tv_context: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, server_default="0"
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_hypothesis_slug"),
        CheckConstraint("ttl_months > 0", name="ck_hypothesis_ttl_positive"),
        Index("ix_hypothesis_status_axis", "status", "axis"),
        Index("ix_hypothesis_precondition_id", "precondition_id"),
        Index("ix_hypothesis_parent_id", "parent_id"),
        Index("ix_hypothesis_expires_at", "expires_at"),
    )


class HypothesisEvaluation(Base):
    __tablename__ = "hypothesis_evaluation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    hypothesis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hypothesis.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status_before: Mapped[str] = mapped_column(String(32), nullable=False)
    status_after: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    invalidator_result: Mapped[dict | None] = mapped_column(JSON(), nullable=True)

    __table_args__ = (
        Index(
            "ix_hypothesis_evaluation_hyp_evaluated",
            "hypothesis_id",
            "evaluated_at",
        ),
    )


# ---------------------------------------------------------------------------
# Phase 2 — vault link
# ---------------------------------------------------------------------------

VALID_STANCES = ("supports", "challenges", "context")
VALID_ADDED_BY = ("operator", "auto")


class HypothesisNodeLink(Base):
    """Pointer from a hypothesis row to a markdown note in the operator's
    knowledge vault.

    Vault path is canonical (e.g. ``Newsletters/lyn-alden/2026-w19.md``);
    not FK-enforced because the indexer's cache lives in a separate SQLite
    DB. The TradingView API validates against the indexer at write time.
    """

    __tablename__ = "hypothesis_node_links"

    hypothesis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hypothesis.id", ondelete="CASCADE"),
        primary_key=True,
    )
    vault_path: Mapped[str] = mapped_column(String(500), primary_key=True)
    stance: Mapped[str] = mapped_column(String(16), nullable=False)
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    added_by: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="operator"
    )

    __table_args__ = (
        Index(
            "ix_hypothesis_node_links_vault_path",
            "vault_path",
        ),
    )
