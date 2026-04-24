from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.auth import verify_api_key
from app.sync import service
from app.sync.schemas import OutboxListResponse, OutboxRow, OutboxStatus, RetryResponse

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/retry", response_model=RetryResponse)
async def retry_outbox(_api_key: str = Depends(verify_api_key)):
    stats = await service.drain_outbox()
    return RetryResponse(**stats)


@router.get("/outbox", response_model=OutboxListResponse)
async def list_outbox(
    status: OutboxStatus = Query("pending"),
    limit: int = Query(200, ge=1, le=1000),
    _api_key: str = Depends(verify_api_key),
):
    rows = await service.list_outbox(status=status, limit=limit)
    return OutboxListResponse(rows=[OutboxRow.model_validate(r) for r in rows])
