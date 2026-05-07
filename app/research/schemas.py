"""Pydantic surface for /v1/research."""
from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    hypothesis_slugs: Optional[list[str]] = None
    # Optional ticker hints for the TV-context gating layer (Phase 4). When
    # any bundled hypothesis has ``requires_tv_context=True`` and any ticker
    # in this list has zero recent tv_context items, the server returns
    # status='needs_context' WITHOUT calling Claude. UI surfaces an attach
    # banner. Operator can re-submit with `force_skip_context_gate=True` to
    # proceed without context.
    tickers: Optional[list[str]] = None
    force_skip_context_gate: bool = False


class EvidenceItem(BaseModel):
    vault_path: str
    title: Optional[str] = None
    section: Optional[str] = None
    text: str = ""
    similarity: float = 0.0
    decay_weight: float = 1.0
    score: float = 0.0
    published_at: Optional[str] = None
    author: Optional[str] = None


class MacroSnapshotItem(BaseModel):
    symbol: str
    latest: float
    latest_ts: str = ""


class SourceContextItem(BaseModel):
    """Operator-authored `_index.md` vignette that applies to one or more
    evidence paths via ancestor-chain walk. No token cap by design."""
    path: str
    title: Optional[str] = None
    body: str = ""
    applies_to: list[str] = Field(default_factory=list)


class TickerContextStatus(BaseModel):
    ticker: str
    available_count: int
    most_recent_at: Optional[datetime.datetime] = None
    needs_context: bool


class AskResponse(BaseModel):
    query_id: str
    answer_path: Optional[str]
    verdict: Optional[str]
    tokens_in: int
    tokens_out: int
    est_cost_usd: float
    proposed_action: Optional[dict[str, Any]] = None
    status: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    macro_state: list[MacroSnapshotItem] = Field(default_factory=list)
    source_context: list[SourceContextItem] = Field(default_factory=list)
    # Phase 4 gating. Populated when status='needs_context' (or whenever
    # tickers were supplied). UI renders ContextNeededBanner from this.
    context_check: list[TickerContextStatus] = Field(default_factory=list)


class ResearchQueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    asked_at: datetime.datetime
    query: str
    hypothesis_ids: list
    answer_path: Optional[str]
    verdict: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    est_cost_usd: Optional[float]
    status: str
    approved_at: Optional[datetime.datetime]
    proposed_action: Optional[dict[str, Any]] = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    macro_state: list[MacroSnapshotItem] = Field(default_factory=list)
    source_context: list[SourceContextItem] = Field(default_factory=list)


class ResearchQueriesList(BaseModel):
    items: list[ResearchQueryRead]
    count: int
