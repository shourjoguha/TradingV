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
    source_context = _service._flatten_source_context(bundle)
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
        source_context=source_context,
        score=row.score,
        is_deferred=row.is_deferred,
        auto_aged_at=row.auto_aged_at,
    )


@router.post("/ask", response_model=AskResponse)
async def ask_endpoint(
    payload: AskRequest,
    _api_key: str = Depends(verify_api_key),
) -> AskResponse:
    result = await _service.ask(
        query=payload.query,
        hypothesis_slugs=payload.hypothesis_slugs,
        tickers=payload.tickers,
        force_skip_context_gate=payload.force_skip_context_gate,
        skill_slug=payload.skill_slug,
    )
    return AskResponse(**result)


@router.get("/skills")
async def list_skills_endpoint(
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """List available research skills (parsed from ``skills/research/*.md``).
    Frontend uses this to populate a skill selector on the Research page."""
    from app.research import skills as _skills
    items = [
        {
            "slug": s.slug,
            "title": s.title,
            "description": s.description,
            "tool": s.tool,
            "default": s.default,
        }
        for s in _skills.list_skills()
    ]
    return {"items": items, "count": len(items)}


@router.get("/queries", response_model=ResearchQueriesList)
async def list_queries(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    order: str = Query("asked_at", pattern="^(asked_at|score)$"),
    include_deferred: bool = Query(True),
    _api_key: str = Depends(verify_api_key),
) -> ResearchQueriesList:
    """List research queries.

    `order=asked_at` (default) preserves the legacy chronological listing —
    backwards-compat for /research detail page and admin tooling.

    `order=score` ranks by composite priority score (top of list = most
    attention-worthy). NULL scores sort last so the Today landing's top-5
    panel surfaces ranked rows first and any unscored legacy queries
    after.

    `include_deferred=false` filters out queries currently in the backlog
    (outside the top-5 visible cohort). Used by the Today landing.
    """
    async with _db.SessionLocal() as session:
        stmt = select(ResearchQuery)
        if status:
            stmt = stmt.where(ResearchQuery.status == status)
        if not include_deferred:
            stmt = stmt.where(ResearchQuery.is_deferred.is_(False))
        if order == "score":
            # NULLs LAST regardless of DB — coalesce to a sentinel that
            # sorts after any real score (any negative number works since
            # our scores can dip below zero with strong penalties, but
            # legacy unscored rows should still trail). Use sqlalchemy
            # nulls_last when available; fall back to coalesce.
            stmt = stmt.order_by(
                desc(ResearchQuery.score.is_not(None)),
                desc(ResearchQuery.score),
                desc(ResearchQuery.asked_at),
            )
        else:
            stmt = stmt.order_by(desc(ResearchQuery.asked_at))
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


@router.delete("/queries/{query_id}")
async def delete_query(
    query_id: str,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    result = await _service.delete(query_id)
    if not result.get("ok"):
        reason = result.get("reason", "delete failed")
        raise HTTPException(404 if reason == "not_found" else 400, reason)
    return result
