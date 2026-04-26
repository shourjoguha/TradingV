"""Prediction comparison endpoints + backfill trigger.

- ``POST /v1/predictions/backfill`` — re-derive prediction_points from existing
  analysis_tasks history.
- ``GET  /v1/predictions/by-target`` — every prediction ever made for one
  (ticker, target_date) + the actual bar.
- ``GET  /v1/predictions/by-horizon`` — multi-ticker grid: for a target_date,
  predictions made N calendar days before across N tickers.

Both reads accept ``?fields=`` (preset like ``ohlc`` OR CSV like
``close,high``) and ``?made_on_dow=4`` (CSV of ints, Mon=0..Sun=6).
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import verify_api_key
from app.predictions import comparison, service

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/by-target")
async def by_target(
    ticker: str = Query(..., min_length=1, max_length=50),
    target_date: datetime.date = Query(...),
    interval: str = Query("1d"),
    model_id: Optional[str] = Query(None),
    fields: Optional[str] = Query(
        None,
        description="Preset (o|h|l|c|v|a|ohlc|ohlcv|all) or CSV (close,high,low).",
    ),
    made_on_dow: Optional[str] = Query(
        None,
        description="CSV of weekday ints (Mon=0..Sun=6). e.g. '4' for Friday.",
    ),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    parsed_fields = comparison.parse_fields(fields)
    parsed_dow = comparison.parse_dow_filter(made_on_dow)
    return await comparison.by_target(
        ticker=ticker,
        target_date=target_date,
        interval=interval,
        model_id=model_id,
        made_on_dow=parsed_dow,
        fields=parsed_fields,
    )


@router.get("/by-horizon")
async def by_horizon(
    target_date: datetime.date = Query(...),
    horizons: str = Query(..., description="CSV of positive ints. e.g. '1,2,3,4,5'."),
    tickers: str = Query(..., description="CSV of symbols. e.g. 'AAPL,MSFT,NVDA'."),
    interval: str = Query("1d"),
    model_id: Optional[str] = Query(None),
    fields: Optional[str] = Query(None),
    made_on_dow: Optional[str] = Query(None),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    try:
        parsed_horizons = [int(h) for h in horizons.split(",") if h.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="horizons must be CSV of integers")
    if not parsed_horizons:
        raise HTTPException(status_code=400, detail="horizons required")

    parsed_tickers = comparison.parse_csv_symbols(tickers)
    if not parsed_tickers:
        raise HTTPException(status_code=400, detail="tickers required")

    parsed_fields = comparison.parse_fields(fields)
    parsed_dow = comparison.parse_dow_filter(made_on_dow)

    rows = await comparison.by_horizon(
        target_date=target_date,
        horizons=parsed_horizons,
        tickers=parsed_tickers,
        interval=interval,
        model_id=model_id,
        made_on_dow=parsed_dow,
        fields=parsed_fields,
    )
    return {
        "target_date": target_date.isoformat(),
        "interval": interval,
        "fields": list(parsed_fields),
        "rows": rows,
    }


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
