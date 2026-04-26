from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class WatchlistEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    added_at: datetime.datetime
    notes: Optional[str] = None


class WatchlistEntryCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=50)
    notes: Optional[str] = Field(None, max_length=2000)


class WatchlistEntryUpdate(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)


class WatchlistListResponse(BaseModel):
    entries: List[WatchlistEntryRead]
    count: int
