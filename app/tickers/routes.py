from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core import db as _db
from app.core.auth import verify_api_key
from app.tickers import service as svc
from app.tickers.schemas import (
    TickerBulkCreate,
    TickerCreate,
    TickerPatch,
    TickerResponse,
)

router = APIRouter(prefix="/tickers", tags=["tickers"])


@router.get("", response_model=List[TickerResponse])
async def list_tickers(
    asset_class: Optional[str] = Query(None, pattern="^(stock|etf|crypto)$"),
    q: Optional[str] = Query(None, description="search substring"),
    limit: int = Query(500, ge=1, le=5000),
    _api_key: str = Depends(verify_api_key),
):
    async with _db.SessionLocal() as session:
        rows = await svc.list_tickers(session, asset_class=asset_class, q=q, limit=limit)
        return rows


@router.get("/search", response_model=List[TickerResponse])
async def search_tickers(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
    _api_key: str = Depends(verify_api_key),
):
    async with _db.SessionLocal() as session:
        return await svc.list_tickers(session, q=q, limit=limit)


@router.post("", response_model=List[TickerResponse])
async def create_tickers(
    body: TickerBulkCreate | TickerCreate,
    _api_key: str = Depends(verify_api_key),
):
    items = body.tickers if isinstance(body, TickerBulkCreate) else [body]
    async with _db.SessionLocal() as session:
        out = []
        for item in items:
            row = await svc.upsert_ticker(
                session,
                item.symbol,
                source="manual",
                asset_class=item.asset_class,
                notes=item.notes,
            )
            out.append(row)
        await session.commit()
        # Re-read to pick up server defaults
        refreshed = [await svc.get_ticker(session, r.symbol) for r in out]
        return refreshed


@router.patch("/{symbol}", response_model=TickerResponse)
async def patch_ticker(
    symbol: str,
    body: TickerPatch,
    _api_key: str = Depends(verify_api_key),
):
    async with _db.SessionLocal() as session:
        row = await svc.patch_ticker(
            session, symbol, asset_class=body.asset_class, notes=body.notes
        )
        if row is None:
            raise HTTPException(status_code=404, detail="ticker not found")
        await session.commit()
        return await svc.get_ticker(session, symbol)


@router.get("/{symbol}", response_model=TickerResponse)
async def get_ticker(symbol: str, _api_key: str = Depends(verify_api_key)):
    async with _db.SessionLocal() as session:
        row = await svc.get_ticker(session, symbol)
        if row is None:
            raise HTTPException(status_code=404, detail="ticker not found")
        return row
