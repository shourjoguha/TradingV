"""Agents lane HTTP surface — /v1/agents/*.

Read + manual-trigger endpoints for the multi-agent decision engine. The daily
background loop (gated by AGENTS_ENABLED) lives in ``app/main.py``; these routes
let the operator pull the latest decisions and force a run on demand.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.agents import service as agents_service
from app.agents.adapter import STANCES, get_engine
from app.core.auth import verify_api_key
from app.core.config import SETTINGS

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentDecisionResponse(BaseModel):
    id: str
    ticker: str
    made_on: Optional[str] = None
    engine: str
    engine_version: str
    stance: str
    confidence: Optional[float] = None
    rationale_md: Optional[str] = None
    transcript_ref: Optional[str] = None
    created_at: Optional[str] = None


class EngineInfoResponse(BaseModel):
    enabled: bool
    active_engine: str
    stances: List[str]


@router.get("/engine", response_model=EngineInfoResponse)
async def engine_info(_api_key: str = Depends(verify_api_key)):
    """What's wired right now: enabled flag + active engine."""
    return EngineInfoResponse(
        enabled=SETTINGS.AGENTS_ENABLED,
        active_engine=get_engine().name,
        stances=list(STANCES),
    )


@router.get("/decisions", response_model=List[AgentDecisionResponse])
async def list_decisions(
    ticker: Optional[str] = Query(None),
    stance: Optional[str] = Query(None, description="BUY | SELL | HOLD"),
    limit: int = Query(100, ge=1, le=1000),
    _api_key: str = Depends(verify_api_key),
):
    if stance is not None and stance.upper() not in STANCES:
        raise HTTPException(status_code=400, detail=f"invalid stance; expected one of {STANCES}")
    rows = await agents_service.list_decisions(ticker=ticker, stance=stance, limit=limit)
    return [AgentDecisionResponse(**r) for r in rows]


class RunRequest(BaseModel):
    ticker: Optional[str] = None  # one ticker; omit to run the whole watchlist


@router.post("/run")
async def run(body: RunRequest, _api_key: str = Depends(verify_api_key)):
    """Manually trigger a decision. One ticker if given, else the watchlist roster.

    Returns 422 with the underlying message when the engine isn't wired
    (AGENTS_ENABLED=false and DEBUG_STUB=false) so the failure is explicit.
    """
    try:
        if body.ticker:
            return await agents_service.run_for_ticker(body.ticker)
        return await agents_service.run_for_watchlist()
    except NotImplementedError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
