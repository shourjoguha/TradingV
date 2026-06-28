"""ORM models for the content/video-series hierarchy.

Mirrors the platform's own information architecture (atomic chunk -> rollup
-> domain) as Domain -> Series -> Arc -> Episode. See
`.claude/plans/video-series-platform-design.md` for the design + rationale.

The load-bearing invariant is **verifiability** (inherited from the
demo-branch discipline in CLAUDE.md): a *published* episode must cite a real
`source_ref` (an ADR / retro / commit). Enforced both by a CHECK constraint
here and by the service layer.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    JSON,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


EPISODE_STATUSES = ("idea", "scripted", "filmed", "published")


class ContentDomain(Base):
    """Top-level fork point (e.g. 'trading'). A new domain reuses the same
    template machinery with different content — the video analogue of the
    vault's finance/fitness/nutrition fork."""

    __tablename__ = "content_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="active"
    )
    order_idx: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    series: Mapped[list["ContentSeries"]] = relationship(
        back_populates="domain", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("slug", name="uq_content_domains_slug"),)


class ContentSeries(Base):
    """The durable promise a subscriber signs up for."""

    __tablename__ = "content_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("content_domains.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    promise: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="active"
    )
    order_idx: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    domain: Mapped["ContentDomain"] = relationship(back_populates="series")
    arcs: Mapped[list["ContentArc"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("domain_id", "slug", name="uq_content_series_domain_slug"),
    )


class ContentArc(Base):
    """A thematic cluster of episodes — the returning-viewer path and the
    long-form explainer destination."""

    __tablename__ = "content_arcs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("content_series.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    theme: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    order_idx: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    series: Mapped["ContentSeries"] = relationship(back_populates="arcs")
    episodes: Mapped[list["ContentEpisode"]] = relationship(
        back_populates="arc", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("series_id", "slug", name="uq_content_arcs_series_slug"),
    )


class ContentEpisode(Base):
    """The atomic unit — one self-contained idea, recut across formats.

    `formats` holds a single set of per-platform URLs (personal-handle
    publishing decision, 2026-05-25): {"tiktok": url, "reels": url,
    "shorts": url, "youtube": url}.
    """

    __tablename__ = "content_episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    arc_id: Mapped[int] = mapped_column(
        ForeignKey("content_arcs.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    hook_text: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    hook_pattern: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    beat_sheet: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="idea"
    )
    # Verifiability anchor: a published episode must trace to a real artifact
    # (e.g. 'adr:007', 'retro:2026-05-16-vault-phase-e', 'commit:<sha>').
    source_ref: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    formats: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, nullable=True)
    order_idx: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    arc: Mapped["ContentArc"] = relationship(back_populates="episodes")

    __table_args__ = (
        UniqueConstraint("arc_id", "slug", name="uq_content_episodes_arc_slug"),
        CheckConstraint(
            "status IN ('idea','scripted','filmed','published')",
            name="ck_content_episodes_status",
        ),
        CheckConstraint(
            "status <> 'published' OR source_ref IS NOT NULL",
            name="ck_content_episodes_published_needs_source",
        ),
        Index("ix_content_episodes_status", "status"),
    )
