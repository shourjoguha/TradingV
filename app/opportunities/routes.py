"""Opportunities routes — Phase 3.1/3.2.

- ``GET    /v1/opportunities``                 — list (filter by status, ticker)
- ``POST   /v1/opportunities/generate``        — manual run of the rule engine
- ``POST   /v1/opportunities/expire``          — sweep expired opportunities
- ``PATCH  /v1/opportunities/{id}``            — transition status (acted/dismissed)
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import verify_api_key
from app.opportunities import service

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("")
async def list_opps(
    status: Optional[str] = Query(None, description="open|acted|dismissed|expired"),
    ticker: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    items = await service.list_opportunities(status=status, ticker=ticker, limit=limit)
    return {"items": items, "count": len(items)}


@router.post("/generate")
async def generate(
    since_hours: int = Query(24, ge=1, le=24 * 30),
    limit: int = Query(1000, ge=1, le=10_000),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, int]:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=since_hours
    )
    return await service.generate_for_predictions(since=since, limit=limit)


@router.post("/expire")
async def expire(_api_key: str = Depends(verify_api_key)) -> dict[str, int]:
    n = await service.expire_stale()
    return {"expired": n}


class StatusUpdate(BaseModel):
    status: str  # 'acted' | 'dismissed' | 'open'
    dismissed_reason: Optional[str] = None


@router.patch("/{opportunity_id}")
async def update(
    opportunity_id: str,
    body: StatusUpdate = Body(...),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    try:
        updated = await service.update_status(
            opportunity_id=opportunity_id,
            status=body.status,
            dismissed_reason=body.dismissed_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return updated
