from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core import db as _db
from app.core.auth import verify_api_key
from app.kronos import service as kservice
from app.kronos.registry import ModelSpec, load_models
from app.kronos.validator import EligibilityValidator, eligible_models_for
from app.market_data import service as md_service
from app.market_data.intervals import is_canonical
from app.tickers import service as tickers_svc

router = APIRouter(tags=["kronos"])


class ModelResponse(BaseModel):
    id: str
    display_name: str
    params_millions: float
    context_length: int
    supported_intervals: List[str]
    supported_asset_classes: List[str]
    required_features: List[str]
    min_history_bars: int
    max_horizon_bars: int
    default_horizon_bars: int
    unverified: bool
    notes: str

    @classmethod
    def from_spec(cls, spec: ModelSpec) -> "ModelResponse":
        return cls(
            id=spec.id,
            display_name=spec.display_name,
            params_millions=spec.params_millions,
            context_length=spec.context_length,
            supported_intervals=list(spec.supported_intervals),
            supported_asset_classes=list(spec.supported_asset_classes),
            required_features=list(spec.required_features),
            min_history_bars=spec.min_history_bars,
            max_horizon_bars=spec.max_horizon_bars,
            default_horizon_bars=spec.default_horizon_bars,
            unverified=spec.unverified,
            notes=spec.notes,
        )


class EligibilityResponse(BaseModel):
    kind: str  # "eligible" | "ineligible"
    model_id: Optional[str] = None
    horizon_bars: Optional[int] = None
    context_length: Optional[int] = None
    unverified: Optional[bool] = None
    reason: Optional[str] = None
    message: Optional[str] = None


@router.get("/models", response_model=List[ModelResponse])
async def list_models(
    asset_class: Optional[str] = Query(None),
    interval: Optional[str] = Query(None),
    _api_key: str = Depends(verify_api_key),
):
    """Registered Kronos models, optionally filtered by asset/interval."""
    if interval is not None and not is_canonical(interval):
        raise HTTPException(status_code=400, detail=f"unsupported interval '{interval}'")
    specs = list(load_models())
    if asset_class is not None:
        specs = [s for s in specs if asset_class in s.supported_asset_classes]
    if interval is not None:
        specs = [s for s in specs if interval in s.supported_intervals]
    return [ModelResponse.from_spec(s) for s in specs]


@router.get("/timeframes", response_model=List[str])
async def list_timeframes(
    ticker: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    _api_key: str = Depends(verify_api_key),
):
    """Intervals eligible for (ticker, model). Never surfaces an unsupported combo."""
    specs = list(load_models())
    if model_id is not None:
        specs = [s for s in specs if s.id == model_id]
        if not specs:
            raise HTTPException(status_code=404, detail=f"unknown model '{model_id}'")

    asset_class: Optional[str] = None
    if ticker is not None:
        async with _db.SessionLocal() as session:
            t = await tickers_svc.get_ticker(session, ticker)
        if t is None:
            # Symbol not yet registered — infer class without persisting.
            from app.tickers.asset_class import infer_asset_class

            asset_class = infer_asset_class(tickers_svc.normalize(ticker))
        else:
            asset_class = t.asset_class
        specs = [s for s in specs if asset_class in s.supported_asset_classes]

    intervals: set[str] = set()
    for s in specs:
        intervals.update(s.supported_intervals)
    # Deterministic ordering by canonical catalog.
    from app.market_data.intervals import CANONICAL_INTERVALS

    return [i for i in CANONICAL_INTERVALS if i in intervals]


@router.get("/eligibility", response_model=EligibilityResponse)
async def check_eligibility(
    model_id: str = Query(...),
    ticker: str = Query(...),
    interval: str = Query(...),
    horizon_bars: Optional[int] = Query(None, ge=1),
    _api_key: str = Depends(verify_api_key),
):
    """Pre-flight eligibility check. Surfaces the same Ineligible reasons the
    analysis orchestrator will raise, so the UI can disable bad combos early."""
    if not is_canonical(interval):
        raise HTTPException(status_code=400, detail=f"unsupported interval '{interval}'")

    sym = tickers_svc.normalize(ticker)
    async with _db.SessionLocal() as session:
        t = await tickers_svc.get_ticker(session, sym)
    if t is None:
        from app.tickers.asset_class import infer_asset_class

        asset_class = infer_asset_class(sym)
    else:
        asset_class = t.asset_class

    available_bars = await md_service.count_cached(sym, interval)
    result = EligibilityValidator.check(
        model_id=model_id,
        asset_class=asset_class,
        interval=interval,
        available_bars=available_bars,
        available_features=kservice.CACHE_FEATURES,
        horizon_bars=horizon_bars,
    )
    if result.kind == "eligible":
        return EligibilityResponse(
            kind="eligible",
            model_id=result.model_id,
            horizon_bars=result.horizon_bars,
            context_length=result.context_length,
            unverified=result.unverified,
        )
    return EligibilityResponse(kind="ineligible", reason=result.reason.value, message=result.message)
