"""Macro Workbench routes — Phase M-1.

- ``GET  /v1/macro/series``  — cached time-series for one symbol.
- ``GET  /v1/macro/ratio``   — numerator/denominator ratio (computed on demand).
- ``POST /v1/macro/refresh`` — manual trigger of upstream refresh.
"""
from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import verify_api_key
from app.macro import service
from app.macro.schemas import (
    MacroPoint,
    MacroRatioResponse,
    MacroRefreshResponse,
    MacroSeriesResponse,
    MacroSpreadResponse,
)

router = APIRouter(prefix="/macro", tags=["macro"])


@router.get("/series", response_model=MacroSeriesResponse)
async def get_series(
    symbol: str = Query(..., min_length=1, max_length=64),
    since: Optional[datetime.date] = Query(None),
    until: Optional[datetime.date] = Query(None),
    _api_key: str = Depends(verify_api_key),
) -> MacroSeriesResponse:
    rows = await service.get_series(symbol, since=since, until=until)
    return MacroSeriesResponse(
        symbol=symbol,
        source=None,
        points=[MacroPoint(ts=r["ts"], value=r["value"]) for r in rows],
    )


@router.get("/ratio", response_model=MacroRatioResponse)
async def get_ratio(
    numerator: str = Query(..., min_length=1, max_length=64),
    denominator: str = Query(..., min_length=1, max_length=64),
    since: Optional[datetime.date] = Query(None),
    until: Optional[datetime.date] = Query(None),
    _api_key: str = Depends(verify_api_key),
) -> MacroRatioResponse:
    rows = await service.compute_ratio(
        numerator=numerator, denominator=denominator, since=since, until=until
    )
    return MacroRatioResponse(
        numerator=numerator,
        denominator=denominator,
        points=[MacroPoint(ts=r["ts"], value=r["value"]) for r in rows],
    )


@router.get("/spread", response_model=MacroSpreadResponse)
async def get_spread(
    minuend: str = Query(..., min_length=1, max_length=64),
    subtrahend: str = Query(..., min_length=1, max_length=64),
    since: Optional[datetime.date] = Query(None),
    until: Optional[datetime.date] = Query(None),
    _api_key: str = Depends(verify_api_key),
) -> MacroSpreadResponse:
    rows = await service.compute_spread(
        minuend=minuend, subtrahend=subtrahend, since=since, until=until,
    )
    return MacroSpreadResponse(
        minuend=minuend,
        subtrahend=subtrahend,
        points=[MacroPoint(ts=r["ts"], value=r["value"]) for r in rows],
    )


@router.post("/refresh", response_model=MacroRefreshResponse)
async def refresh(
    symbol: Optional[str] = Query(
        None, description="Refresh just this symbol; default = all in registry."
    ),
    _api_key: str = Depends(verify_api_key),
) -> MacroRefreshResponse:
    if symbol is not None:
        try:
            n = await service.refresh(symbol)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return MacroRefreshResponse(
            rows_touched=n,
            ok=1 if n > 0 else 0,
            failed=0,
            skipped=1 if n == 0 else 0,
            failures=[],
        )

    stats = await service.refresh_all()
    return MacroRefreshResponse(**stats)
