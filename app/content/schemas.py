"""Pydantic shapes for /v1/content/* endpoints.

See `.claude/plans/video-series-platform-design.md`.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ---- Reads (nested tree) ----------------------------------------------------


class EpisodeRead(BaseModel):
    id: int
    arc_id: int
    slug: str
    title: str
    hook_text: Optional[str] = None
    hook_pattern: Optional[str] = None
    beat_sheet: Optional[Dict[str, Any]] = None
    status: str
    source_ref: Optional[str] = None
    formats: Optional[Dict[str, str]] = None
    order_idx: int
    published_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime


class ArcRead(BaseModel):
    id: int
    series_id: int
    slug: str
    title: str
    theme: Optional[str] = None
    order_idx: int
    created_at: datetime.datetime
    episodes: List[EpisodeRead] = []


class SeriesRead(BaseModel):
    id: int
    domain_id: int
    slug: str
    title: str
    promise: Optional[str] = None
    status: str
    order_idx: int
    created_at: datetime.datetime
    arcs: List[ArcRead] = []


class DomainRead(BaseModel):
    id: int
    slug: str
    title: str
    status: str
    order_idx: int
    created_at: datetime.datetime
    series: List[SeriesRead] = []


class ContentTree(BaseModel):
    domains: List[DomainRead] = []


# ---- Writes -----------------------------------------------------------------


class DomainCreate(BaseModel):
    slug: str
    title: str
    order_idx: int = 0


class SeriesCreate(BaseModel):
    domain_id: int
    slug: str
    title: str
    promise: Optional[str] = None
    order_idx: int = 0


class ArcCreate(BaseModel):
    series_id: int
    slug: str
    title: str
    theme: Optional[str] = None
    order_idx: int = 0


class EpisodeCreate(BaseModel):
    arc_id: int
    slug: str
    title: str
    hook_text: Optional[str] = None
    hook_pattern: Optional[str] = None
    beat_sheet: Optional[Dict[str, Any]] = None
    source_ref: Optional[str] = None
    order_idx: int = 0


class EpisodeUpdate(BaseModel):
    """All optional — PATCH semantics. `status='published'` requires a
    resolvable `source_ref` (verifiability invariant)."""

    title: Optional[str] = None
    hook_text: Optional[str] = None
    hook_pattern: Optional[str] = None
    beat_sheet: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    source_ref: Optional[str] = None
    formats: Optional[Dict[str, str]] = None
    order_idx: Optional[int] = None
