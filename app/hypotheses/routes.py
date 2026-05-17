"""HTTP surface for hypotheses + the lifespan force-fire debug endpoint."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core import db as _db
from app.core.auth import verify_api_key
from app.hypotheses import service
from app.hypotheses.models import ALL_CLAIM_TYPES, ALL_STATUSES
from app.hypotheses.schemas import (
    EvaluationRead,
    HypothesisCancel,
    HypothesisCreate,
    HypothesisHealthItem,
    HypothesisHealthList,
    HypothesisListResponse,
    HypothesisPatch,
    HypothesisRead,
)

router = APIRouter(prefix="/hypotheses", tags=["hypotheses"])


def _serialize(hyp, evals=None) -> HypothesisRead:
    return HypothesisRead(
        id=hyp.id,
        slug=hyp.slug,
        title=hyp.title,
        claim_type=hyp.claim_type,
        axis=hyp.axis,
        parent_id=hyp.parent_id,
        precondition_id=hyp.precondition_id,
        primary_metric=hyp.primary_metric,
        tracking_signal=hyp.tracking_signal,
        invalidator=hyp.invalidator,
        ttl_months=hyp.ttl_months,
        created_at=hyp.created_at,
        expires_at=hyp.expires_at,
        status=hyp.status,
        body_md=hyp.body_md,
        recent_evaluations=[EvaluationRead.model_validate(e) for e in (evals or [])],
    )


@router.get("", response_model=HypothesisListResponse)
async def list_hypotheses(
    status: Optional[str] = Query(None),
    axis: Optional[str] = Query(None),
    claim_type: Optional[str] = Query(None),
    _api_key: str = Depends(verify_api_key),
) -> HypothesisListResponse:
    if status and status not in ALL_STATUSES:
        raise HTTPException(400, f"status must be one of {ALL_STATUSES}")
    if claim_type and claim_type not in ALL_CLAIM_TYPES:
        raise HTTPException(400, f"claim_type must be one of {ALL_CLAIM_TYPES}")
    async with _db.SessionLocal() as session:
        rows = await service.list_(
            session, status=status, axis=axis, claim_type=claim_type
        )
        items = [_serialize(r) for r in rows]
    return HypothesisListResponse(items=items, count=len(items))


@router.get("/summary")
async def get_summary(_api_key: str = Depends(verify_api_key)) -> dict:
    """Counts by status + ``at_risk`` (active rows expiring within 30d).

    Powers the sidebar widget.
    """
    async with _db.SessionLocal() as session:
        return await service.summary(session)


@router.post("", response_model=HypothesisRead, status_code=201)
async def create_hypothesis(
    payload: HypothesisCreate,
    _api_key: str = Depends(verify_api_key),
) -> HypothesisRead:
    async with _db.SessionLocal() as session:
        existing = await service.get_by_slug(session, payload.slug)
        if existing:
            raise HTTPException(409, f"slug already exists: {payload.slug}")
        # Optional FK references must point to existing rows.
        for fk_field in ("parent_id", "precondition_id"):
            ref = getattr(payload, fk_field)
            if ref and not await service.get(session, ref):
                raise HTTPException(400, f"{fk_field} not found: {ref}")
        row = await service.create(session, payload)
        await session.commit()
    return _serialize(row)


@router.get("/{hyp_id}", response_model=HypothesisRead)
async def get_hypothesis(
    hyp_id: str,
    _api_key: str = Depends(verify_api_key),
) -> HypothesisRead:
    async with _db.SessionLocal() as session:
        row = await service.get(session, hyp_id)
        if not row:
            raise HTTPException(404, "hypothesis not found")
        evals = await service.recent_evaluations(session, hyp_id)
    return _serialize(row, evals=evals)


@router.patch("/{hyp_id}", response_model=HypothesisRead)
async def patch_hypothesis(
    hyp_id: str,
    payload: HypothesisPatch,
    _api_key: str = Depends(verify_api_key),
) -> HypothesisRead:
    async with _db.SessionLocal() as session:
        row = await service.get(session, hyp_id)
        if not row:
            raise HTTPException(404, "hypothesis not found")
        for fk_field in ("parent_id", "precondition_id"):
            ref = getattr(payload, fk_field)
            if ref and not await service.get(session, ref):
                raise HTTPException(400, f"{fk_field} not found: {ref}")
        row = await service.patch(session, row, payload)
        await session.commit()
    return _serialize(row)


@router.delete("/{hyp_id}", status_code=204)
async def delete_hypothesis(
    hyp_id: str,
    _api_key: str = Depends(verify_api_key),
) -> None:
    async with _db.SessionLocal() as session:
        row = await service.get(session, hyp_id)
        if not row:
            raise HTTPException(404, "hypothesis not found")
        await service.delete(session, row)
        await session.commit()


@router.post("/{hyp_id}/cancel", response_model=EvaluationRead)
async def cancel_hypothesis(
    hyp_id: str,
    payload: HypothesisCancel,
    _api_key: str = Depends(verify_api_key),
) -> EvaluationRead:
    async with _db.SessionLocal() as session:
        row = await service.get(session, hyp_id)
        if not row:
            raise HTTPException(404, "hypothesis not found")
        ev = await service.cancel(session, row, payload)
        await session.commit()
        return EvaluationRead.model_validate(ev)


@router.post("/_tick", response_model=dict)
async def force_tick(_api_key: str = Depends(verify_api_key)) -> dict:
    """Force the daily lifespan tick. Operator/test-only — same logic the
    nightly scheduler runs."""
    async with _db.SessionLocal() as session:
        stats = await service.run_daily_tick(session)
        await session.commit()
        return stats


@router.get("/health/list", response_model=HypothesisHealthList)
async def list_hypothesis_health(
    limit: int = 200,
    _api_key: str = Depends(verify_api_key),
) -> HypothesisHealthList:
    """Operator-friendly health view for the rx finance panel (v1.x.1-b).

    Returns each hypothesis with age, days-to-expiry, and a count of
    finance recs (last 30d) whose tldr|body_md mentions the title.
    """
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be in [1,500]")
    rows = await service.list_health(limit=limit)
    items = [HypothesisHealthItem(**r) for r in rows]
    return HypothesisHealthList(items=items, count=len(items))
