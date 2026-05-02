"""Pydantic surface for /v1/research."""
from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    hypothesis_slugs: Optional[list[str]] = None


class AskResponse(BaseModel):
    query_id: str
    answer_path: Optional[str]
    verdict: Optional[str]
    tokens_in: int
    tokens_out: int
    est_cost_usd: float
    proposed_action: Optional[dict[str, Any]] = None
    status: str


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


class ResearchQueriesList(BaseModel):
    items: list[ResearchQueryRead]
    count: int
