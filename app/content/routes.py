"""HTTP surface for the content/video-series hierarchy.

  GET   /v1/content/tree                  — full Domain->Series->Arc->Episode tree
  GET   /v1/content/episodes              — flat episode list (kanban), ?status=
  POST  /v1/content/domains               — create a domain
  POST  /v1/content/series                — create a series
  POST  /v1/content/arcs                  — create an arc
  POST  /v1/content/episodes              — create an episode (always 'idea')
  PATCH /v1/content/episodes/{episode_id} — update fields / status / formats

See `.claude/plans/video-series-platform-design.md`.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from app.content import service
from app.content.models import (
    ContentArc,
    ContentDomain,
    ContentEpisode,
    ContentSeries,
)
from app.content.schemas import (
    ArcCreate,
    ArcRead,
    ContentTree,
    DomainCreate,
    DomainRead,
    EpisodeCreate,
    EpisodeRead,
    EpisodeUpdate,
    SeriesCreate,
    SeriesRead,
)
from app.core.auth import verify_api_key


router = APIRouter(prefix="/content", tags=["content"])


def _sorted(rows):
    return sorted(rows or [], key=lambda r: (r.order_idx, r.id))


def _episode_read(row: ContentEpisode) -> EpisodeRead:
    return EpisodeRead(
        id=row.id,
        arc_id=row.arc_id,
        slug=row.slug,
        title=row.title,
        hook_text=row.hook_text,
        hook_pattern=row.hook_pattern,
        beat_sheet=row.beat_sheet,
        status=row.status,
        source_ref=row.source_ref,
        formats=row.formats,
        order_idx=row.order_idx,
        published_at=row.published_at,
        created_at=row.created_at,
    )


def _arc_read(row: ContentArc, *, children: bool = True) -> ArcRead:
    episodes = [_episode_read(e) for e in _sorted(row.episodes)] if children else []
    return ArcRead(
        id=row.id,
        series_id=row.series_id,
        slug=row.slug,
        title=row.title,
        theme=row.theme,
        order_idx=row.order_idx,
        created_at=row.created_at,
        episodes=episodes,
    )


def _series_read(row: ContentSeries, *, children: bool = True) -> SeriesRead:
    arcs = [_arc_read(a) for a in _sorted(row.arcs)] if children else []
    return SeriesRead(
        id=row.id,
        domain_id=row.domain_id,
        slug=row.slug,
        title=row.title,
        promise=row.promise,
        status=row.status,
        order_idx=row.order_idx,
        created_at=row.created_at,
        arcs=arcs,
    )


def _domain_read(row: ContentDomain, *, children: bool = True) -> DomainRead:
    series = [_series_read(s) for s in _sorted(row.series)] if children else []
    return DomainRead(
        id=row.id,
        slug=row.slug,
        title=row.title,
        status=row.status,
        order_idx=row.order_idx,
        created_at=row.created_at,
        series=series,
    )


# ---- Reads ------------------------------------------------------------------


@router.get("/tree", response_model=ContentTree)
async def get_tree(
    domain: Optional[str] = None,
    _api_key: str = Depends(verify_api_key),
) -> ContentTree:
    domains = await service.get_tree(domain_slug=domain)
    return ContentTree(domains=[_domain_read(d) for d in domains])


@router.get("/episodes", response_model=List[EpisodeRead])
async def list_episodes(
    status: Optional[str] = None,
    limit: int = 200,
    _api_key: str = Depends(verify_api_key),
) -> List[EpisodeRead]:
    rows = await service.list_episodes(status=status, limit=limit)
    return [_episode_read(r) for r in rows]


# ---- Creates ----------------------------------------------------------------


@router.post("/domains", response_model=DomainRead)
async def create_domain(
    body: DomainCreate,
    _api_key: str = Depends(verify_api_key),
) -> DomainRead:
    try:
        row = await service.create_domain(
            slug=body.slug, title=body.title, order_idx=body.order_idx
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"domain slug {body.slug!r} exists")
    return _domain_read(row, children=False)


@router.post("/series", response_model=SeriesRead)
async def create_series(
    body: SeriesCreate,
    _api_key: str = Depends(verify_api_key),
) -> SeriesRead:
    try:
        row = await service.create_series(
            domain_id=body.domain_id,
            slug=body.slug,
            title=body.title,
            promise=body.promise,
            order_idx=body.order_idx,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="series slug exists in this domain")
    return _series_read(row, children=False)


@router.post("/arcs", response_model=ArcRead)
async def create_arc(
    body: ArcCreate,
    _api_key: str = Depends(verify_api_key),
) -> ArcRead:
    try:
        row = await service.create_arc(
            series_id=body.series_id,
            slug=body.slug,
            title=body.title,
            theme=body.theme,
            order_idx=body.order_idx,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="arc slug exists in this series")
    return _arc_read(row, children=False)


@router.post("/episodes", response_model=EpisodeRead)
async def create_episode(
    body: EpisodeCreate,
    _api_key: str = Depends(verify_api_key),
) -> EpisodeRead:
    try:
        row = await service.create_episode(
            arc_id=body.arc_id,
            slug=body.slug,
            title=body.title,
            hook_text=body.hook_text,
            hook_pattern=body.hook_pattern,
            beat_sheet=body.beat_sheet,
            source_ref=body.source_ref,
            order_idx=body.order_idx,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="episode slug exists in this arc")
    return _episode_read(row)


@router.patch("/episodes/{episode_id}", response_model=EpisodeRead)
async def update_episode(
    episode_id: int,
    body: EpisodeUpdate,
    _api_key: str = Depends(verify_api_key),
) -> EpisodeRead:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    try:
        row = await service.update_episode(episode_id, fields=fields)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _episode_read(row)
