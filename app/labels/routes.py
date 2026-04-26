"""Ticker label CRUD.

Mounted at ``/v1/tickers/{symbol}/labels`` to keep the URL hierarchy
consistent with other ticker-scoped data. The replication receiver lives
at ``/v1/labels/import`` (top-level — symbol is in the body, not path).
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from app.core.auth import verify_api_key
from app.labels import service
from app.labels.schemas import (
    LabelRead,
    LabelsBulkUpsert,
    LabelsListResponse,
    LabelUpsert,
)

router = APIRouter(prefix="/tickers/{symbol}/labels", tags=["labels"])
import_router = APIRouter(prefix="/labels", tags=["labels"])


@import_router.post("/import", response_model=dict)
async def import_label_change(
    payload: Dict[str, Any] = Body(...),
    _api_key: str = Depends(verify_api_key),
):
    """Replication receiver. Bypasses the replication enqueue path."""
    result = await service.apply_imported_change(payload)
    return {"result": result}


@router.get("", response_model=LabelsListResponse)
async def list_labels(symbol: str, _api_key: str = Depends(verify_api_key)):
    rows = await service.list_labels(symbol)
    return LabelsListResponse(
        symbol=symbol.upper().strip(),
        labels=[LabelRead.model_validate(r) for r in rows],
    )


@router.put("", response_model=LabelsListResponse)
async def bulk_upsert_labels(
    symbol: str,
    body: LabelsBulkUpsert,
    _api_key: str = Depends(verify_api_key),
):
    rows = await service.bulk_upsert(symbol, body.labels)
    return LabelsListResponse(
        symbol=symbol.upper().strip(),
        labels=[LabelRead.model_validate(r) for r in rows],
    )


@router.get("/{key}", response_model=LabelRead)
async def get_label(symbol: str, key: str, _api_key: str = Depends(verify_api_key)):
    row = await service.get_label(symbol, key)
    if row is None:
        raise HTTPException(status_code=404, detail=f"label '{key}' not set for {symbol}")
    return LabelRead.model_validate(row)


@router.put("/{key}", response_model=LabelRead)
async def upsert_label(
    symbol: str,
    key: str,
    body: LabelUpsert,
    _api_key: str = Depends(verify_api_key),
):
    row = await service.upsert_label(symbol, key, body.value)
    return LabelRead.model_validate(row)


@router.delete("/{key}", status_code=204)
async def delete_label(symbol: str, key: str, _api_key: str = Depends(verify_api_key)):
    removed = await service.delete_label(symbol, key)
    if not removed:
        raise HTTPException(status_code=404, detail=f"label '{key}' not set for {symbol}")
    return None
