"""Queue routes — Tier 1 job submission queue.

Visibility + lifecycle:
- ``GET    /v1/analysis/queue``           list (filter by status)
- ``GET    /v1/analysis/queue/stats``     status counts (powers Dashboard widget)
- ``GET    /v1/analysis/queue/{id}``      single-item poll
- ``POST   /v1/analysis/queue``           manual enqueue (rare; main path is /v1/analysis/run)
- ``DELETE /v1/analysis/queue/{id}``      cancel pending
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.analysis.schemas import AnalysisRunRequest
from app.core.auth import verify_api_key
from app.queue import service as _qsvc

router = APIRouter(prefix="/analysis/queue", tags=["analysis-queue"])


@router.get("")
async def list_queue(
    status: Optional[str] = Query(None, description="pending|running|done|failed|cancelled"),
    limit: int = Query(50, ge=1, le=500),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    items = await _qsvc.list_items(status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/stats")
async def queue_stats(_api_key: str = Depends(verify_api_key)) -> dict[str, int]:
    return await _qsvc.queue_stats()


@router.get("/{queue_id}")
async def get_queue_item(
    queue_id: str, _api_key: str = Depends(verify_api_key)
) -> dict[str, Any]:
    item = await _qsvc.get(queue_id)
    if item is None:
        raise HTTPException(status_code=404, detail="queue item not found")
    return item


@router.post("")
async def enqueue_manual(
    body: AnalysisRunRequest, _api_key: str = Depends(verify_api_key)
) -> dict[str, Any]:
    """Manual enqueue. Same effect as POST /v1/analysis/run; provided for
    explicit queue-API symmetry."""
    return await _qsvc.enqueue(inputs=body.model_dump(), source="manual")


@router.delete("/{queue_id}")
async def cancel_queue_item(
    queue_id: str, _api_key: str = Depends(verify_api_key)
) -> dict[str, Any]:
    ok, current = await _qsvc.cancel(queue_id)
    if current == "not_found":
        raise HTTPException(status_code=404, detail="queue item not found")
    if not ok:
        raise HTTPException(
            status_code=409, detail=f"cannot cancel item in status '{current}'"
        )
    return {"cancelled": True, "id": queue_id}
