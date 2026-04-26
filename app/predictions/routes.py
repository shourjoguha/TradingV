"""Prediction endpoints. v1: backfill trigger only.

Phase 5 will add:
  - GET /v1/predictions/by-target?ticker=&target_date=
  - GET /v1/predictions/by-horizon?made_on=&horizon=&tickers=

Both with ``?fields=`` and ``?made_on_dow=`` filters.
"""
from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.auth import verify_api_key
from app.predictions import service

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("/backfill")
async def backfill(
    since: Optional[datetime.date] = Query(
        None, description="Only consider tasks with started_at >= this date."
    ),
    only_missing: bool = Query(
        True,
        description="Skip tasks already exploded. Set false to rewrite.",
    ),
    _api_key: str = Depends(verify_api_key),
):
    """Re-derive ``prediction_points`` from existing ``analysis_tasks`` history.

    Idempotent. Run-once after migration 0009 to seed the table from
    META/AAPL/NVDA jobs that were run before this feature shipped.
    """
    stats = await service.backfill_all(since=since, only_missing=only_missing)
    return stats
