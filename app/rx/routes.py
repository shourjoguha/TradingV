"""HTTP surface for the rx (prescription) layer — finance only.

Endpoints (all under /v1/rx):
  POST /recs                          — ingest (X-RX-Ingest-Token auth)
  GET  /recs                          — list (X-API-Key auth)
  GET  /recs/{rec_id}                 — detail
  POST /recs/{rec_id}/disposition     — operator disposition write
  POST /recs/{rec_id}/snooze          — operator snooze write

The split auth model is intentional: ingest comes from the laptop's
`/rx-finance` slash command over a separate shared secret so that a
compromised ingest token cannot be used to read/disposition existing
recs (and vice versa). See app/core/auth.py for the rationale.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_api_key, verify_rx_ingest_token
from app.rx import service
from app.rx.models import Recommendation
from app.rx.service import _FORCED_DECISION_SNOOZE_COUNT
from app.rx.schemas import (
    DispositionWrite,
    RecCreate,
    RecList,
    RecListItem,
    RecRead,
    RxLinkHypothesis,
    RxLinkTrade,
    RxLinks,
    SnoozeWrite,
)


router = APIRouter(prefix="/rx", tags=["rx"])


def _to_read(row: Recommendation) -> RecRead:
    return RecRead(
        id=row.id,
        owner_user_id=row.owner_user_id,
        domain=row.domain,
        status=row.status,
        drift_score=row.drift_score,
        confidence=row.confidence,
        tldr=row.tldr,
        body_md=row.body_md,
        rx_md_path=row.rx_md_path,
        facts_json=row.facts_json,
        source_refs=row.source_refs,
        signals_fired=row.signals_fired,
        drift_breakdown=row.drift_breakdown,
        confidence_breakdown=row.confidence_breakdown,
        acted_disposition=row.acted_disposition,
        acted_at=row.acted_at,
        subjective_fit_1_5=row.subjective_fit_1_5,
        next_session_id=row.next_session_id,
        outcome_note=row.outcome_note,
        snoozed_until=row.snoozed_until,
        snooze_count=row.snooze_count or 0,
        created_at=row.created_at,
        forced_decision=(row.snooze_count or 0)
        >= _FORCED_DECISION_SNOOZE_COUNT,
        attention_score=row.attention_score,
        attention_breakdown=row.attention_breakdown,
    )


@router.post("/recs", response_model=RecRead, status_code=201)
async def create_rec(
    payload: RecCreate,
    _token: str = Depends(verify_rx_ingest_token),
) -> RecRead:
    """Ingest a new finance recommendation from the laptop generator."""
    try:
        row = await service.create(
            domain=payload.domain,
            drift_score=payload.drift_score,
            confidence=payload.confidence,
            tldr=payload.tldr,
            body_md=payload.body_md,
            rx_md_path=payload.rx_md_path,
            facts_json=payload.facts_json,
            source_refs=payload.source_refs,
            signals_fired=payload.signals_fired,
            drift_breakdown=payload.drift_breakdown,
            confidence_breakdown=payload.confidence_breakdown,
            created_at=payload.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _to_read(row)


@router.get("/recs", response_model=RecList)
async def list_recs(
    window_days: int = 60,
    limit: int = 200,
    _api_key: str = Depends(verify_api_key),
) -> RecList:
    """List finance recs in the rolling window (default 60d, max 200)."""
    if window_days < 1 or window_days > 365:
        raise HTTPException(
            status_code=400, detail="window_days must be in [1,365]"
        )
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=400, detail="limit must be in [1,500]"
        )
    items_raw = await service.list_recs(
        window_days=window_days, limit=limit
    )
    items = [RecListItem(**it) for it in items_raw]
    return RecList(items=items, count=len(items))


@router.get("/recs/{rec_id}", response_model=RecRead)
async def get_rec(
    rec_id: str,
    _api_key: str = Depends(verify_api_key),
) -> RecRead:
    row = await service.get(rec_id)
    if row is None:
        raise HTTPException(status_code=404, detail="rec not found")
    return _to_read(row)


@router.post("/recs/{rec_id}/disposition", response_model=RecRead)
async def disposition_rec(
    rec_id: str,
    body: DispositionWrite,
    _api_key: str = Depends(verify_api_key),
) -> RecRead:
    try:
        row = await service.disposition(
            rec_id,
            disposition=body.disposition,
            subjective_fit_1_5=body.subjective_fit_1_5,
            outcome_note=body.outcome_note,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_read(row)


@router.post("/recs/{rec_id}/snooze", response_model=RecRead)
async def snooze_rec(
    rec_id: str,
    body: SnoozeWrite,
    _api_key: str = Depends(verify_api_key),
) -> RecRead:
    try:
        row = await service.snooze(rec_id, days=body.days)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_read(row)


@router.get("/recs/{rec_id}/links", response_model=RxLinks)
async def rec_links(
    rec_id: str,
    _api_key: str = Depends(verify_api_key),
) -> RxLinks:
    """Heuristic links: hypotheses + trades mentioned by this rec.

    Hypotheses: title-substring in (tldr || body_md), case-insensitive.
    Trades: explicit FK (trades.related_rec_id) UNION ticker mentioned in
    the rec text. See `service.links_for_rec` for full semantics.
    """
    try:
        out = await service.links_for_rec(rec_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return RxLinks(
        hypotheses=[RxLinkHypothesis(**h) for h in out["hypotheses"]],
        trades=[RxLinkTrade(**t) for t in out["trades"]],
    )
