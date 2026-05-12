"""/v1/earnings — read endpoints.

Manual refresh routes through the generic
``POST /v1/admin/loops/earnings_calendar/fire`` so we don't duplicate the
fire-now plumbing.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import verify_api_key
from app.earnings import service as _svc


router = APIRouter(prefix="/earnings", tags=["earnings"])


@router.get("/upcoming")
async def upcoming(
    days: int = Query(30, ge=1, le=180),
    _api_key: str = Depends(verify_api_key),
) -> dict:
    items = await _svc.upcoming_earnings(days=days)
    return {"items": items, "count": len(items)}


@router.get("/{ticker}")
async def get_one(
    ticker: str,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    row = await _svc.get_for_ticker(ticker)
    if row is None:
        raise HTTPException(404, f"no earnings row for ticker {ticker!r}")
    return row


@router.get("/")
async def list_all(_api_key: str = Depends(verify_api_key)) -> dict:
    items = await _svc.upcoming_earnings(days=180)
    return {"items": items, "count": len(items)}
