"""Read-only demo routes. All payloads are pre-baked JSON loaded once
at import time via lru_cache. Mutating endpoint look-alikes (ack,
update) return the cached payload unchanged so the frontend's
optimistic UI keeps working without state actually changing.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.demo.ask_match import match_query

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "demo-data"


@lru_cache(maxsize=64)
def _load(rel_path: str) -> Any:
    p = DATA_DIR / rel_path
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"snapshot file missing: {rel_path}")
    return json.loads(p.read_text(encoding="utf-8"))


# --- Manifest / Today ---------------------------------------------------

@router.get("/manifest")
async def manifest() -> Any:
    return _load("manifest.json")


@router.get("/today")
async def today() -> Any:
    return _load("today.json")


# --- Predictions --------------------------------------------------------

@router.get("/predictions/by-horizon")
async def predictions_by_horizon() -> Any:
    return _load("predictions/by-horizon.json")


@router.get("/predictions/by-target")
async def predictions_by_target() -> Any:
    return _load("predictions/by-target.json")


@router.get("/accuracy/grid")
async def accuracy_grid() -> Any:
    return _load("predictions/accuracy.json")


# --- Motion -------------------------------------------------------------

@router.get("/opportunities")
async def opportunities() -> Any:
    return _load("motion/opportunities.json")


@router.get("/trades")
async def trades() -> Any:
    return _load("motion/trades.json")


# --- Mutating look-alikes (no-op stubs) --------------------------------

@router.post("/accuracy/drift/{drift_id}/ack")
async def ack_drift(drift_id: str) -> dict[str, Any]:
    return {"id": drift_id, "acknowledged": True, "demo": True}


@router.patch("/opportunities/{opp_id}")
async def update_opportunity(opp_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": opp_id, "updated": True, "demo": True, "body": body or {}}


# --- Ask ----------------------------------------------------------------

class AskRequest(BaseModel):
    q: str


class AskResponse(BaseModel):
    match: str  # "exact" | "fuzzy" | "miss"
    answer_id: str | None
    answer: dict[str, Any] | None
    suggestions: list[dict[str, str]]


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest) -> AskResponse:
    canned = _load("canned.json")
    result = match_query(body.q, canned)
    answer = None
    if result["answer_id"]:
        for entry in canned.get("answers", []):
            if entry["id"] == result["answer_id"]:
                answer = entry
                break
    return AskResponse(
        match=result["match"],
        answer_id=result["answer_id"],
        answer=answer,
        suggestions=result["suggestions"],
    )
