from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.core.auth import verify_api_key
from app.labels import service as labels_svc
from app.watchlist import service
from app.watchlist.schemas import (
    WatchlistEntryCreate,
    WatchlistEntryRead,
    WatchlistEntryUpdate,
    WatchlistListResponse,
)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=WatchlistListResponse)
async def list_watchlist(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    labels: Optional[str] = Query(
        None,
        description="Filter by labels: 'sector:tech,capsize:large'. ALL must match.",
    ),
    _api_key: str = Depends(verify_api_key),
):
    entries = await service.list_entries(limit=limit, offset=offset)
    if labels:
        pairs = labels_svc.parse_labels_filter(labels)
        if pairs:
            allowed = await labels_svc.filter_symbols_by_labels(pairs)
            entries = [e for e in entries if e.symbol in allowed]
    return WatchlistListResponse(
        entries=[WatchlistEntryRead.model_validate(e) for e in entries],
        count=len(entries),
    )


@router.post("", response_model=WatchlistEntryRead, status_code=201)
async def add_to_watchlist(
    body: WatchlistEntryCreate,
    _api_key: str = Depends(verify_api_key),
):
    entry = await service.add_entry(body.symbol, notes=body.notes)
    return WatchlistEntryRead.model_validate(entry)


@router.post("/bulk", response_model=dict)
async def bulk_add(
    symbols: List[str] = Body(..., embed=True),
    _api_key: str = Depends(verify_api_key),
):
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols required")
    added = await service.bulk_add(symbols)
    return {"requested": len(symbols), "added": added}


@router.get("/{symbol}", response_model=WatchlistEntryRead)
async def get_watchlist_entry(symbol: str, _api_key: str = Depends(verify_api_key)):
    entry = await service.get_entry(symbol)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"'{symbol}' not on watchlist")
    return WatchlistEntryRead.model_validate(entry)


@router.patch("/{symbol}", response_model=WatchlistEntryRead)
async def update_watchlist_entry(
    symbol: str,
    body: WatchlistEntryUpdate,
    _api_key: str = Depends(verify_api_key),
):
    entry = await service.update_entry(symbol, notes=body.notes)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"'{symbol}' not on watchlist")
    return WatchlistEntryRead.model_validate(entry)


@router.delete("/{symbol}", status_code=204)
async def remove_from_watchlist(symbol: str, _api_key: str = Depends(verify_api_key)):
    removed = await service.remove_entry(symbol)
    if not removed:
        raise HTTPException(status_code=404, detail=f"'{symbol}' not on watchlist")
    return None


# ----------------------------------------------------------------------
# Replication receiver. NOT for human use — called by the peer's outbox
# drain. Idempotent. Bypasses the replication enqueue path to avoid loops.
# ----------------------------------------------------------------------

@router.post("/import", response_model=dict)
async def import_watchlist_change(
    payload: dict = Body(...),
    _api_key: str = Depends(verify_api_key),
):
    result = await service.apply_imported_change(payload)
    return {"result": result}
