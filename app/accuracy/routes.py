"""Accuracy routes — Phase 1.1.

- ``GET  /v1/accuracy/grid`` — per-(ticker, horizon) summary for the dashboard.
- ``GET  /v1/accuracy/pair`` — drilldown rows for one (ticker, horizon, model).
- ``POST /v1/accuracy/evaluate`` — manual trigger of the evaluator (idempotent).
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.accuracy import drift, service
from app.core.auth import verify_api_key

router = APIRouter(prefix="/accuracy", tags=["accuracy"])


def _parse_csv_strings(spec: Optional[str]) -> Optional[list[str]]:
    if not spec:
        return None
    return [s.strip() for s in spec.split(",") if s.strip()]


def _parse_csv_ints(spec: Optional[str]) -> Optional[list[int]]:
    if not spec:
        return None
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid int in CSV: {part}")
    return out or None


@router.get("/grid")
async def grid(
    tickers: Optional[str] = Query(None, description="CSV. Default: all tickers."),
    horizons: Optional[str] = Query(None, description="CSV of int offsets. Default: all."),
    model_id: Optional[str] = Query(None),
    last_n: int = Query(30, ge=1, le=500),
    since: Optional[datetime.date] = Query(None),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    rows = await service.accuracy_grid(
        tickers=_parse_csv_strings(tickers),
        horizons=_parse_csv_ints(horizons),
        model_id=model_id,
        last_n=last_n,
        since=since,
    )
    return {"rows": rows, "window_size": last_n}


@router.get("/pair")
async def pair(
    ticker: str = Query(..., min_length=1, max_length=50),
    horizon_offset: int = Query(..., ge=1),
    model_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    rows = await service.pair_history(
        ticker=ticker,
        horizon_offset=horizon_offset,
        model_id=model_id,
        limit=limit,
    )
    return {"ticker": ticker, "horizon_offset": horizon_offset, "rows": rows}


@router.post("/evaluate")
async def evaluate(
    limit: int = Query(500, ge=1, le=10_000, description="Max prediction_points to scan."),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, int]:
    """Manual trigger. Same code path as the lifespan loop. Idempotent."""
    return await service.evaluate_pending(limit=limit)


@router.get("/drift")
async def list_drift(
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Open (unacknowledged) drift alerts. Powers dashboard banner."""
    alerts = await drift.list_open_alerts()
    return {"alerts": alerts}


@router.post("/drift/detect")
async def trigger_drift_detection(
    notify: bool = Query(True, description="Send Telegram on new alerts."),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Manual drift scan. Same code path as the lifespan loop. Idempotent."""
    new = await drift.detect_drift(notify=notify)
    return {"new_alerts": [{"id": a.id, "ticker": a.ticker, "ratio": a.ratio} for a in new]}


@router.post("/drift/{alert_id}/ack")
async def ack_drift(
    alert_id: str,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, bool]:
    """Mark a drift alert acknowledged. Allows future re-flag for the same pair."""
    ok = await drift.acknowledge_alert(alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="alert not found or already acked")
    return {"acknowledged": True}
