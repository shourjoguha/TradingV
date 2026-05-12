from __future__ import annotations

import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AnalysisRunRequest(BaseModel):
    tickers: List[str] = Field(..., min_length=1)
    intervals: List[str] = Field(..., min_length=1)
    model_ids: Optional[List[str]] = None  # None = all registered models
    horizon_bars: Optional[int] = Field(None, ge=1)


class AnalysisRunResponse(BaseModel):
    """Returned by POST /v1/analysis/run.

    Tier-1 queue: the request is queued, not run inline. ``queue_id`` is
    populated; ``job_id`` stays None until the worker picks it up. Frontend
    polls /v1/analysis/queue/{queue_id} until status='done', then jumps to
    the job_id field.
    """
    queue_id: str
    status: str  # 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
    job_id: Optional[str] = None
    # Legacy fields kept for backwards-compat — populated when status='done'
    # via the queue polling endpoint, not by this initial response.
    task_count: Optional[int] = None


class AnalysisTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticker: str
    interval: str
    model_id: str
    status: str
    result_json: Optional[dict[str, Any]] = None
    ineligible_reason: Optional[str] = None
    ineligible_message: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime.datetime] = None
    finished_at: Optional[datetime.datetime] = None


class AnalysisJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    task_count: int
    submitted_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None

    # Per-task outcome buckets — aggregated by ``service.list_jobs`` so
    # the frontend's collapsed-row outcome bar can render eagerly without
    # one detail-fetch per row. ``pending`` is queued-but-not-started;
    # ``running`` is in-flight.
    done: int = 0
    ineligible: int = 0
    error: int = 0
    running: int = 0
    pending: int = 0


class AnalysisJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    task_count: int
    submitted_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None
    origin: Optional[str] = None
    tasks: List[AnalysisTaskResponse]


class AnalysisImportResponse(BaseModel):
    job_id: str
    status: str  # "imported" | "duplicate"
