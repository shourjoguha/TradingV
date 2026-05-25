"""content service — Domain/Series/Arc/Episode CRUD + tree assembly.

Verifiability invariant (see CLAUDE.md demo-branch discipline): an episode
may only move to ``status='published'`` if it carries a non-empty
``source_ref``. Enforced here AND by a DB CHECK constraint in the model.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.content.models import (
    EPISODE_STATUSES,
    ContentArc,
    ContentDomain,
    ContentEpisode,
    ContentSeries,
)
from app.core import db as _db


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


# ---- Creates ----------------------------------------------------------------


async def create_domain(*, slug: str, title: str, order_idx: int = 0) -> ContentDomain:
    row = ContentDomain(slug=slug, title=title, order_idx=order_idx)
    async with _db.SessionLocal() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def create_series(
    *, domain_id: int, slug: str, title: str, promise: Optional[str] = None, order_idx: int = 0
) -> ContentSeries:
    row = ContentSeries(
        domain_id=domain_id, slug=slug, title=title, promise=promise, order_idx=order_idx
    )
    async with _db.SessionLocal() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def create_arc(
    *, series_id: int, slug: str, title: str, theme: Optional[str] = None, order_idx: int = 0
) -> ContentArc:
    row = ContentArc(
        series_id=series_id, slug=slug, title=title, theme=theme, order_idx=order_idx
    )
    async with _db.SessionLocal() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def create_episode(
    *,
    arc_id: int,
    slug: str,
    title: str,
    hook_text: Optional[str] = None,
    hook_pattern: Optional[str] = None,
    beat_sheet: Optional[Dict[str, Any]] = None,
    source_ref: Optional[str] = None,
    order_idx: int = 0,
) -> ContentEpisode:
    """Episodes are always created in 'idea' status. Promotion to
    'published' goes through ``update_episode`` so the verifiability guard
    fires."""
    row = ContentEpisode(
        arc_id=arc_id,
        slug=slug,
        title=title,
        hook_text=hook_text,
        hook_pattern=hook_pattern,
        beat_sheet=beat_sheet,
        source_ref=source_ref,
        order_idx=order_idx,
        status="idea",
    )
    async with _db.SessionLocal() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


# ---- Episode update (with verifiability guard) ------------------------------


def _is_blank(value: Optional[str]) -> bool:
    return value is None or not str(value).strip()


async def update_episode(episode_id: int, *, fields: Dict[str, Any]) -> ContentEpisode:
    """Patch an episode. Raises:

    * ``LookupError`` if the episode does not exist.
    * ``ValueError`` for an invalid status, or for a 'published' transition
      without a resolvable ``source_ref`` (verifiability invariant).
    """
    new_status = fields.get("status")
    if new_status is not None and new_status not in EPISODE_STATUSES:
        raise ValueError(
            f"status must be one of {EPISODE_STATUSES}, got {new_status!r}"
        )

    async with _db.SessionLocal() as session:
        row = await session.get(ContentEpisode, episode_id)
        if row is None:
            raise LookupError(f"episode {episode_id} not found")

        # Resolve the effective source_ref (incoming wins, else existing).
        effective_source = (
            fields["source_ref"] if "source_ref" in fields else row.source_ref
        )
        if new_status == "published" and _is_blank(effective_source):
            raise ValueError(
                "cannot publish an episode without a source_ref "
                "(verifiability invariant)"
            )

        for key, value in fields.items():
            setattr(row, key, value)

        # Stamp published_at on the first transition into 'published'.
        if new_status == "published" and row.published_at is None:
            row.published_at = _utcnow()

        await session.commit()
        await session.refresh(row)
        return row


# ---- Reads ------------------------------------------------------------------


async def list_episodes(
    *, status: Optional[str] = None, limit: int = 200
) -> List[ContentEpisode]:
    """Flat episode list (kanban backend), optionally filtered by status."""
    async with _db.SessionLocal() as session:
        stmt = select(ContentEpisode)
        if status is not None:
            stmt = stmt.where(ContentEpisode.status == status)
        stmt = stmt.order_by(ContentEpisode.order_idx, ContentEpisode.id).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_tree(*, domain_slug: Optional[str] = None) -> List[ContentDomain]:
    """Full nested Domain -> Series -> Arc -> Episode tree, eager-loaded so
    the route can serialize without lazy-load on detached instances."""
    async with _db.SessionLocal() as session:
        stmt = (
            select(ContentDomain)
            .options(
                selectinload(ContentDomain.series)
                .selectinload(ContentSeries.arcs)
                .selectinload(ContentArc.episodes)
            )
            .order_by(ContentDomain.order_idx, ContentDomain.id)
        )
        if domain_slug is not None:
            stmt = stmt.where(ContentDomain.slug == domain_slug)
        result = await session.execute(stmt)
        return list(result.scalars().unique().all())
