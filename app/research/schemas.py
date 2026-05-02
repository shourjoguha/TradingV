"""Pydantic surface for /v1/research."""
from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    hypothesis_slugs: Optional[list[str]] = None


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


class ResearchQueriesList(BaseModel):
    items: list[ResearchQueryRead]
    count: int
