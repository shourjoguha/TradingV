"""Pydantic shapes for /v1/boards/* endpoints (UI calls these "Watchlists")."""
from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel


class BoardCreate(BaseModel):
    name: str
    description: Optional[str] = None


class BoardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class BoardSummary(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    ticker_count: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class BoardTickerOut(BaseModel):
    ticker: str
    notes: Optional[str] = None
    added_at: datetime.datetime
    last_close: Optional[float] = None
    last_close_at: Optional[datetime.date] = None
    pct_1w: Optional[float] = None
    quote_fetched_at: Optional[datetime.datetime] = None


class BoardDetail(BoardSummary):
    tickers: List[BoardTickerOut]


class BoardsList(BaseModel):
    items: List[BoardSummary]


class TickerAddRequest(BaseModel):
    ticker: str
    notes: Optional[str] = None


class TickerMoveRequest(BaseModel):
    ticker: str
    target_board_id: str
