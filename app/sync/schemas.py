from __future__ import annotations

import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class OutboxRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    peer_url: str
    kind: str = "ticker"
    # ticker rows populate symbol/asset_class; result rows leave both NULL.
    symbol: Optional[str] = None
    asset_class: Optional[str] = None
    # Result rows carry payload_json; ticker rows leave it NULL. Excluded
    # from list responses by default to avoid 50KB+ rows in /v1/sync/outbox.
    payload_json: Optional[dict[str, Any]] = None
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
