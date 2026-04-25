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
    include_payload: bool = Query(
        False, description="Include payload_json (large) for result rows."
    ),
    _api_key: str = Depends(verify_api_key),
):
    rows = await service.list_outbox(status=status, limit=limit)
    out: list[OutboxRow] = []
    for r in rows:
        row = OutboxRow.model_validate(r)
        if not include_payload:
            row.payload_json = None
        out.append(row)
    return OutboxListResponse(rows=out)
