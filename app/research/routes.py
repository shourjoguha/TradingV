"""HTTP surface for /v1/research."""
from __future__ import annotations

from typing import Optional

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
        items=[ResearchQueryRead.model_validate(r) for r in rows],
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
    return ResearchQueryRead.model_validate(row)


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
