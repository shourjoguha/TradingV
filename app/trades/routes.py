"""Trade journal routes — Phase 5."""
from __future__ import annotations

import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import verify_api_key
from app.trades import service

router = APIRouter(prefix="/trades", tags=["trades"])


class TradeCreate(BaseModel):
    ticker: str
    side: str  # 'buy' | 'sell'
    qty: float
    entry_price: float
    entry_at: Optional[datetime.datetime] = None
    opportunity_id: Optional[str] = None
    fees: float = 0.0
    notes_md: Optional[str] = None


class TradeUpdate(BaseModel):
    exit_price: Optional[float] = None
    exit_at: Optional[datetime.datetime] = None
    fees: Optional[float] = None
    notes_md: Optional[str] = None


@router.get("")
async def list_(
    ticker: Optional[str] = Query(None),
    opportunity_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    items = await service.list_trades(
        ticker=ticker, opportunity_id=opportunity_id, limit=limit
    )
    summary = await service.pnl_summary()
    return {"items": items, "count": len(items), "pnl_summary": summary}


@router.post("")
async def create(body: TradeCreate, _api_key: str = Depends(verify_api_key)) -> dict[str, Any]:
    try:
        return await service.create_trade(**body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{trade_id}")
async def update(
    trade_id: str,
    body: TradeUpdate,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    updated = await service.update_trade(
        trade_id, **body.model_dump(exclude_none=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="trade not found")
    return updated


@router.get("/pnl/by-rule")
async def pnl_by_rule(_api_key: str = Depends(verify_api_key)) -> dict[str, Any]:
    """Per-opportunity-rule P&L attribution. Closes the feedback loop."""
    return {"rules": await service.pnl_by_rule()}
