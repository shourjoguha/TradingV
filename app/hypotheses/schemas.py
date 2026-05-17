"""Pydantic schemas for the /v1/hypotheses surface."""
from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.hypotheses import invalidator as inv_dsl
from app.hypotheses.models import ALL_CLAIM_TYPES, ALL_STATUSES


class _HypothesisBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    claim_type: str
    axis: str = Field(..., min_length=1, max_length=64)
    primary_metric: str = Field(..., min_length=1, max_length=200)
    tracking_signal: str = Field(..., min_length=1, max_length=200)
    invalidator: dict[str, Any]
    parent_id: Optional[str] = None
    precondition_id: Optional[str] = None
    body_md: Optional[str] = None

    @field_validator("claim_type")
    @classmethod
    def _check_claim_type(cls, v: str) -> str:
        if v not in ALL_CLAIM_TYPES:
            raise ValueError(f"claim_type must be one of {ALL_CLAIM_TYPES}")
        return v

    @field_validator("invalidator")
    @classmethod
    def _check_invalidator(cls, v: dict[str, Any]) -> dict[str, Any]:
        inv_dsl.validate_spec(v)
        return v


class HypothesisCreate(_HypothesisBase):
    slug: str = Field(..., min_length=1, max_length=120)
    # ttl_months is *optional* on create. If omitted, service derives it
    # from the per-claim_type default. If provided, the operator override
    # wins (drafts use this, e.g. btc-bottom-3m has ttl=3 even though
    # claim_type=regime defaults to 30).
    ttl_months: Optional[int] = Field(default=None, gt=0, le=120)


class HypothesisPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    axis: Optional[str] = Field(default=None, min_length=1, max_length=64)
    primary_metric: Optional[str] = Field(default=None, min_length=1, max_length=200)
    tracking_signal: Optional[str] = Field(default=None, min_length=1, max_length=200)
    invalidator: Optional[dict[str, Any]] = None
    parent_id: Optional[str] = None
    precondition_id: Optional[str] = None
    body_md: Optional[str] = None

    @field_validator("invalidator")
    @classmethod
    def _check_invalidator(cls, v):
        if v is None:
            return v
        inv_dsl.validate_spec(v)
        return v


class HypothesisCancel(BaseModel):
    reason: str = Field(..., min_length=1, max_length=300)


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    evaluated_at: datetime.datetime
    status_before: str
    status_after: str
    reason: str
    invalidator_result: Optional[dict[str, Any]] = None


class HypothesisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    title: str
    claim_type: str
    axis: str
    parent_id: Optional[str]
    precondition_id: Optional[str]
    primary_metric: str
    tracking_signal: str
    invalidator: dict[str, Any]
    ttl_months: int
    created_at: datetime.datetime
    expires_at: datetime.datetime
    status: str
    body_md: Optional[str]
    recent_evaluations: list[EvaluationRead] = Field(default_factory=list)


class HypothesisListResponse(BaseModel):
    items: list[HypothesisRead]
    count: int


def _ensure_status(v: str) -> str:
    if v not in ALL_STATUSES:
        raise ValueError(f"status must be one of {ALL_STATUSES}")
    return v


# ---------------------------------------------------------------------------
# Health view (rx v1.x.1-b) — operator-friendly summary for the rx finance
# panel. Lightweight projection over Hypothesis + recommendations.
# ---------------------------------------------------------------------------

class HypothesisHealthItem(BaseModel):
    id: str
    slug: str
    title: str
    status: str
    claim_type: str
    age_days: int
    days_to_expiry: int
    # Heuristic: count of finance recs in the last 30 days whose
    # tldr|body_md contains the hypothesis title (case-insensitive
    # substring). Pre-Phase-I this is the only link signal we have;
    # explicit hypothesis_id FK on recommendations is future work.
    related_recs_count: int


class HypothesisHealthList(BaseModel):
    items: list[HypothesisHealthItem]
    count: int
