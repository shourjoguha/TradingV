"""Pydantic shapes for /v1/ticker-review/* endpoints (Phase D)."""
from __future__ import annotations

import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


class TickerReviewRead(BaseModel):
    id: int
    ticker: str
    first_seen_at: datetime.datetime
    last_seen_at: datetime.datetime
    times_seen: int
    channels: List[str]
    recent_video_ids: List[str]
    recent_caption_snippets: List[str]
    status: str
    resolved_at: Optional[datetime.datetime] = None
    resolved_target: Optional[str] = None
    previously_dismissed_at: Optional[datetime.datetime] = None


class TickerReviewList(BaseModel):
    items: List[TickerReviewRead]


class ResolveRequest(BaseModel):
    action: Literal["add_to_roster", "add_to_board", "dismiss"]
    board_id: Optional[str] = None
