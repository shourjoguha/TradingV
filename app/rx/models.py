"""ORM model for the recommendations table (rx layer, finance-only).

See migrations/versions/0029_recommendations.py for the design rationale.
"""
from __future__ import annotations

import datetime
import uuid
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="open"
    )
    drift_score: Mapped[Optional[float]] = mapped_column(Float(), nullable=True)
    confidence: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    tldr: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    body_md: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    rx_md_path: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    facts_json: Mapped[Optional[Any]] = mapped_column(JSON(), nullable=True)
    source_refs: Mapped[Optional[Any]] = mapped_column(JSON(), nullable=True)
    signals_fired: Mapped[Optional[Any]] = mapped_column(JSON(), nullable=True)
    drift_breakdown: Mapped[Optional[Any]] = mapped_column(JSON(), nullable=True)
    confidence_breakdown: Mapped[Optional[Any]] = mapped_column(JSON(), nullable=True)
    acted_disposition: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    acted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subjective_fit_1_5: Mapped[Optional[int]] = mapped_column(
        Integer(), nullable=True
    )
    next_session_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    outcome_note: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    snoozed_until: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snooze_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # tv-context-decision-engine-enrichment Phase 2: "operator attention"
    # axis. Score is a weighted decayed sum of recent TV-context items
    # mentioning a ticker pulled from the rec's tldr+body_md. Breakdown is
    # per-ticker `{ticker: {kind: count, score: float}}`. Both nullable so
    # legacy rows pre-migration keep working.
    attention_score: Mapped[Optional[float]] = mapped_column(
        Float(), nullable=True
    )
    attention_breakdown: Mapped[Optional[Any]] = mapped_column(
        JSON(), nullable=True
    )
    # retrieval-depth Phase 4 (D2 fix): explicit hypothesis linkage — the
    # list of hypothesis ids this rec acts on, set at compose time. PRIMARY
    # linkage; the substring heuristic in links_for_rec is now only a
    # fallback suggestion. Nullable + additive (legacy rows = None).
    linked_hypothesis_ids: Mapped[Optional[Any]] = mapped_column(
        JSON(), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "domain = 'finance'", name="ck_recommendations_finance_only"
        ),
        CheckConstraint(
            "status IN ('open','snoozed','acted','dismissed')",
            name="ck_recommendations_status",
        ),
        CheckConstraint(
            "subjective_fit_1_5 IS NULL OR (subjective_fit_1_5 BETWEEN 1 AND 5)",
            name="ck_recommendations_subjective_fit",
        ),
        # Index direction matches migration (`created_at DESC`). Without
        # the text() override, create_all builds an ascending index and
        # diverges from alembic-built schemas — harmless functionally but
        # confusing during drift checks.
        Index(
            "ix_recommendations_status_created",
            "status",
            "created_at",
            postgresql_ops={"created_at": "DESC"},
        ),
        Index(
            "ix_recommendations_snoozed_until",
            "snoozed_until",
        ),
        # Every read filters owner_user_id; cheap index keeps the access
        # pattern consistent w/ how the rest of the app slices by tenant.
        Index(
            "ix_recommendations_owner_user_id",
            "owner_user_id",
        ),
    )


class RxDeepResult(Base):
    """Out-of-band enrichment computed in a Claude Code session and POSTed
    back so the always-on app can surface it without making LLM/API calls
    itself.

    The cost seam (retrieval-depth-and-debiasing-program, Phase 0): heavy /
    judgment work — deep multi-hop retrieval, source-contradiction analysis,
    off-vault disconfirmation — runs interactively in Claude Code (no API
    key, subscription-billed), then lands here via POST /v1/rx/deep with the
    ingest token. The app reads it via GET /v1/rx/deep.

    Keyed by EITHER ``rec_id`` (attach to an existing recommendation) OR
    ``query_hash`` (a deep retrieval run not yet tied to a rec). At least one
    is required; both may be set. ``rec_id`` is intentionally NOT a FK — a
    deep run can precede the rec it informs, and we never want enrichment to
    block on referential integrity.
    """

    __tablename__ = "rx_deep_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rec_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    query_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[Any] = mapped_column(JSON(), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('deep_retrieval','contradiction','disconfirmation')",
            name="ck_rx_deep_results_kind",
        ),
        Index("ix_rx_deep_results_rec_id", "rec_id"),
        Index("ix_rx_deep_results_query_hash", "query_hash"),
        Index(
            "ix_rx_deep_results_created",
            "created_at",
            postgresql_ops={"created_at": "DESC"},
        ),
    )
