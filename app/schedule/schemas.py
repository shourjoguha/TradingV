from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScheduleConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    tz_name: str
    run_at_local: datetime.time
    intervals: List[str]
    horizon_bars: int
    model_ids: List[str]
    retry_minutes: int
    collect_actuals: bool
    skip_weekends: bool
    pending_run: bool
    last_run_at: Optional[datetime.datetime] = None
    last_run_status: Optional[str] = None
    last_run_error: Optional[str] = None
    next_run_at: Optional[datetime.datetime] = None
    updated_at: datetime.datetime


class ScheduleConfigUpdate(BaseModel):
    """Partial update — every field optional. Send only what you want to change."""

    enabled: Optional[bool] = None
    tz_name: Optional[str] = Field(None, min_length=1, max_length=64)
    run_at_local: Optional[datetime.time] = None
    intervals: Optional[List[str]] = Field(None, min_length=1)
    horizon_bars: Optional[int] = Field(None, ge=1, le=200)
    model_ids: Optional[List[str]] = Field(None, min_length=1)
    retry_minutes: Optional[int] = Field(None, ge=1, le=120)
    collect_actuals: Optional[bool] = None
    skip_weekends: Optional[bool] = None
