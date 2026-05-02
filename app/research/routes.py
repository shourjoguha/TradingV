"""HTTP surface for /v1/research."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select

from app.core import db as _db
from app.core.auth import verify_api_key
from app.research import service as _service
from app.research.models import ResearchQuery
from app.research.schemas import (
    AskRequest,
    AskResponse,
    ResearchQueriesList,
    ResearchQueryRead,
)

router = APIRouter(prefix="/research", tags=["research"])


def _enriched_read(row: ResearchQuery) -> ResearchQueryRead:
    """Build a ResearchQueryRead with evidence/macro/proposed_action
    re-derived from persisted bundle + response columns."""
    bundle = row.bundle or {}
    evidence = _service._flatten_evidence(bundle)
    macro = _service._flatten_macro(bundle)
    proposed: Optional[dict[str, Any]] = None
    # If approved, prefer the approved_action snapshot.
    if row.approved_action:
        proposed = row.approved_action
    else:
        for tc in (row.response or {}).get("tool_calls", []) or []:
            if tc.get("name") == "propose_invalidator_update":
                proposed = tc.get("input")
                break
    return ResearchQueryRead(
        id=row.id,
        asked_at=row.asked_at,
        query=row.query,
        hypothesis_ids=row.hypothesis_ids or [],
        answer_path=row.answer_path,
        verdict=row.verdict,
        tokens_in=row.tokens_in,
        tokens_out=row.tokens_out,
        est_cost_usd=float(row.est_cost_usd) if row.est_cost_usd is not None else None,
        status=row.status,
        approved_at=row.approved_at,
        proposed_action=proposed,
        evidence=evidence,
        macro_state=macro,
    )


@router.post("/ask", response_model=AskResponse)
async def ask_endpoint(
    payload: AskRequest,
    _api_key: str = Depends(verify_api_key),
) -> AskResponse:
    result = await _service.ask(
        query=payload.query,
        hypothesis_slugs=payload.hypothesis_slugs,
    )
    return AskResponse(**result)


@router.get("/queries", response_model=ResearchQueriesList)
async def list_queries(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    _api_key: str = Depends(verify_api_key),
) -> ResearchQueriesList:
    async with _db.SessionLocal() as session:
        stmt = select(ResearchQuery).order_by(desc(ResearchQuery.asked_at))
        if status:
            stmt = stmt.where(ResearchQuery.status == status)
        stmt = stmt.limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()
    return ResearchQueriesList(
        items=[_enriched_read(r) for r in rows],
        count=len(rows),
    )


@router.get("/queries/{query_id}", response_model=ResearchQueryRead)
async def get_query(
    query_id: str,
    _api_key: str = Depends(verify_api_key),
) -> ResearchQueryRead:
    async with _db.SessionLocal() as session:
        row = await session.get(ResearchQuery, query_id)
        if row is None:
            raise HTTPException(404, "research query not found")
    return _enriched_read(row)


@router.post("/queries/{query_id}/approve")
async def approve_query(
    query_id: str,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    result = await _service.approve(query_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "approve failed"))
    return result


@router.post("/queries/{query_id}/dismiss")
async def dismiss_query(
    query_id: str,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    result = await _service.dismiss(query_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "dismiss failed"))
    return result
