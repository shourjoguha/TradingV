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
    job_id: str
    task_count: int
    status: str


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


class AnalysisJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    task_count: int
    submitted_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None
    tasks: List[AnalysisTaskResponse]
