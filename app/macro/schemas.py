"""Pydantic response shapes for /v1/macro endpoints."""
from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel


class MacroPoint(BaseModel):
    ts: datetime.date
    value: float


class MacroSeriesResponse(BaseModel):
    symbol: str
    source: Optional[str] = None
    points: List[MacroPoint]


class MacroRatioResponse(BaseModel):
    numerator: str
    denominator: str
    points: List[MacroPoint]


class MacroRefreshResponse(BaseModel):
    rows_touched: int
    ok: int
    failed: int
    skipped: int
    failures: List[str] = []
