"""Pydantic in/out schemas for tv_context ingest + retrieval."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


KindLiteral = Literal["webhook", "screenshot", "note", "idea", "event"]
StatusLiteral = Literal["active", "expired", "archived"]


class WebhookIngest(BaseModel):
    """Pine-script alert payload. Kept loose: TV operator defines the
    payload shape inside Pine, we only require enough to bin and dedupe.
    """

    ticker: str
    alert_type: str
    payload_json: Dict[str, Any] = Field(default_factory=dict)
    source: str = "tradingview"
    expires_at: Optional[datetime.datetime] = None


class NoteIngest(BaseModel):
    ticker: Optional[str] = None
    body: str
    tags: List[str] = Field(default_factory=list)
    expires_at: Optional[datetime.datetime] = None


class IdeaIngest(BaseModel):
    ticker: Optional[str] = None
    url: str
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    expires_at: Optional[datetime.datetime] = None


class EventIngest(BaseModel):
    ticker: Optional[str] = None
    label: str  # e.g. "Q3 earnings", "FOMC"
    event_date: datetime.date
    body: Optional[str] = None
    expires_at: Optional[datetime.datetime] = None


class TVContextItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: KindLiteral
    ticker: Optional[str]
    source: str
    captured_at: datetime.datetime
    expires_at: Optional[datetime.datetime]
    status: StatusLiteral
    payload: Dict[str, Any]
    tombstone: Optional[Dict[str, Any]]
    vault_path: Optional[str]
    heavy_blob_dropped: bool


class IngestResult(BaseModel):
    item: Optional[TVContextItemOut]
    deduped: bool = False
    dedupe_count: Optional[int] = None


class VisionSpendOut(BaseModel):
    month: str  # YYYY-MM
    total_usd: float
    call_count: int


class ContextCheckResult(BaseModel):
    """Result of `recent_for_ticker` check used by gating layer."""

    ticker: str
    available_count: int
    most_recent_at: Optional[datetime.datetime] = None
    needs_context: bool


class ScreenshotIngestMeta(BaseModel):
    """Multipart form metadata accompanying the binary upload."""

    ticker: str
    note: Optional[str] = None
    hypothesis_id: Optional[str] = None
    vision_enabled: Optional[bool] = None  # None = use config default
    expires_at: Optional[datetime.datetime] = None
