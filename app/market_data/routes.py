import datetime
import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core import db as _db
from app.core.auth import verify_api_key
from app.market_data import service
from app.market_data.derived import TickerMarketData
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


# ---------------------------------------------------------------------------
# Quotes — lightweight last close + 1w pct for a list of symbols.
# ---------------------------------------------------------------------------

class QuotePoint(BaseModel):
    symbol: str
    last_close: float | None = None
    last_close_at: datetime.date | None = None
    pct_1w: float | None = None
    quote_fetched_at: datetime.datetime | None = None


class QuotesResponse(BaseModel):
    items: List[QuotePoint]


@router.get("/quotes", response_model=QuotesResponse)
async def get_quotes(
    symbols: str = Query(..., description="CSV of symbols, e.g. AAPL,MSFT,NVDA"),
    _api_key: str = Depends(verify_api_key),
):
    """Read-only bulk fetch of cached `last_close + pct_1w` for the given
    symbols. Powers the casual Watchlists rows + the macro sector
    drill-in. Symbols missing a `ticker_market_data` row return with all
    fields null — caller decides how to render that.
    """
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return QuotesResponse(items=[])

    async with _db.SessionLocal() as session:
        rows = (
            await session.execute(
                select(TickerMarketData).where(TickerMarketData.symbol.in_(syms))
            )
        ).scalars().all()
    by_symbol: dict[str, TickerMarketData] = {r.symbol: r for r in rows}
    out: List[QuotePoint] = []
    for sym in syms:
        r = by_symbol.get(sym)
        if r is None:
            out.append(QuotePoint(symbol=sym))
        else:
            out.append(
                QuotePoint(
                    symbol=sym,
                    last_close=float(r.last_close) if r.last_close is not None else None,
                    last_close_at=r.last_close_at,
                    pct_1w=float(r.pct_1w) if r.pct_1w is not None else None,
                    quote_fetched_at=r.quote_fetched_at,
                )
            )
    return QuotesResponse(items=out)
