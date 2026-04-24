from __future__ import annotations

import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class OutboxRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    peer_url: str
    symbol: str
    asset_class: str
    attempts: int
    last_error: Optional[str] = None
    next_retry_at: datetime.datetime
    created_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None


class RetryResponse(BaseModel):
    scanned: int
    ok: int
    failed: int


OutboxStatus = Literal["pending", "completed", "failed"]


class OutboxListResponse(BaseModel):
    rows: List[OutboxRow]
