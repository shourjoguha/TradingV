"""HTTP surface for the ticker-review queue (Phase D).

Endpoints:
  GET  /v1/ticker-review/queue        — list (Today strip + admin)
  POST /v1/ticker-review/{id}/resolve — resolve action (chains to watchlist/boards)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_api_key
from app.ticker_review import service
from app.ticker_review.models import TickerReviewEntry
from app.ticker_review.schemas import (
    ResolveRequest,
    TickerReviewList,
    TickerReviewRead,
)


router = APIRouter(prefix="/ticker-review", tags=["ticker-review"])


def _to_read(row: TickerReviewEntry) -> TickerReviewRead:
    return TickerReviewRead(
        id=row.id,
        ticker=row.ticker,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        times_seen=row.times_seen,
        channels=list(row.channels or []),
        recent_video_ids=list(row.recent_video_ids or []),
        recent_caption_snippets=list(row.recent_caption_snippets or []),
        status=row.status,
        resolved_at=row.resolved_at,
        resolved_target=row.resolved_target,
        previously_dismissed_at=row.previously_dismissed_at,
    )


@router.get("/queue", response_model=TickerReviewList)
async def get_queue(
    status: Optional[str] = None,
    limit: int = 50,
    _api_key: str = Depends(verify_api_key),
) -> TickerReviewList:
    """Pending entries by default; pass ``status=all`` for the full set."""
    if status in (None, "pending"):
        rows = await service.list_pending(limit=limit)
    elif status == "all":
        rows = await service.list_all(limit=limit)
    else:
        rows = await service.list_all(status=status, limit=limit)
    return TickerReviewList(items=[_to_read(r) for r in rows])


@router.post("/{entry_id}/resolve", response_model=TickerReviewRead)
async def resolve_entry(
    entry_id: int,
    body: ResolveRequest,
    _api_key: str = Depends(verify_api_key),
) -> TickerReviewRead:
    try:
        row = await service.resolve(
            entry_id, action=body.action, board_id=body.board_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_read(row)
