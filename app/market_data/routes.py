import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import verify_api_key
from app.market_data import service
from app.market_data.intervals import CANONICAL_INTERVALS, is_canonical
from app.market_data.providers.base import UnsupportedRequest
from app.market_data.schemas import BarResponse, OhlcvResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["market_data"])


@router.get("/intervals", response_model=List[str])
async def list_intervals(_api_key: str = Depends(verify_api_key)):
    """Canonical intervals the platform can ingest. Not yet filtered by model
    eligibility — that's the Kronos registry's job (Phase 3)."""
    return list(CANONICAL_INTERVALS)


@router.get("/ohlcv", response_model=OhlcvResponse)
async def get_ohlcv(
    symbol: str = Query(..., min_length=1),
    interval: str = Query(..., description="canonical interval, e.g. 1d"),
    limit: int = Query(500, ge=1, le=5000),
    refresh: bool = Query(False, description="pull fresh bars from provider before returning"),
    _api_key: str = Depends(verify_api_key),
):
    if not is_canonical(interval):
        raise HTTPException(
            status_code=400,
            detail=f"unsupported interval '{interval}'. valid: {list(CANONICAL_INTERVALS)}",
        )

    if refresh:
        try:
            await service.refresh(symbol, interval)
        except UnsupportedRequest as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:  # pragma: no cover - provider failure path
            logger.error("refresh failed for %s %s: %s", symbol, interval, e)
            raise HTTPException(status_code=502, detail=f"provider error: {e}")

    bars = await service.get_cached(symbol, interval, limit=limit)
    return OhlcvResponse(
        symbol=service.normalize(symbol),
        interval=interval,
        count=len(bars),
        bars=[BarResponse.model_validate(b) for b in bars],
    )
