"""TV-context HTTP routes."""
from __future__ import annotations

import datetime
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.core import db as _db
from app.core.auth import verify_api_key
from app.tv_context import service as _svc
from app.tv_context.schemas import (
    EventIngest,
    IdeaIngest,
    IngestResult,
    NoteIngest,
    TVContextItemOut,
    VisionSpendOut,
    WebhookIngest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tv-context", tags=["tv_context"])


def _to_out(item) -> TVContextItemOut:
    return TVContextItemOut.model_validate(item)


@router.post("/webhook", response_model=IngestResult)
async def post_webhook(
    body: WebhookIngest, _api_key: str = Depends(verify_api_key)
):
    async with _db.SessionLocal() as session:
        item, deduped = await _svc.ingest_webhook(
            session=session,
            ticker=body.ticker,
            alert_type=body.alert_type,
            payload_json=body.payload_json,
            source=body.source,
            expires_at=body.expires_at,
        )
        await session.commit()
        await session.refresh(item)
        dedupe_count = (item.payload or {}).get("dedupe_count", 1) if deduped else None
        return IngestResult(
            item=_to_out(item),
            deduped=deduped,
            dedupe_count=dedupe_count,
        )


@router.post("/note", response_model=IngestResult)
async def post_note(body: NoteIngest, _api_key: str = Depends(verify_api_key)):
    async with _db.SessionLocal() as session:
        item = await _svc.ingest_note(
            session=session,
            ticker=body.ticker,
            body=body.body,
            tags=body.tags,
            expires_at=body.expires_at,
        )
        await session.commit()
        await session.refresh(item)
        return IngestResult(item=_to_out(item))


@router.post("/idea", response_model=IngestResult)
async def post_idea(body: IdeaIngest, _api_key: str = Depends(verify_api_key)):
    if "tradingview.com" not in body.url.lower():
        raise HTTPException(
            status_code=400,
            detail="idea url must be a tradingview.com permalink",
        )
    async with _db.SessionLocal() as session:
        item = await _svc.ingest_idea(
            session=session,
            ticker=body.ticker,
            url=body.url,
            summary=body.summary,
            tags=body.tags,
            expires_at=body.expires_at,
        )
        await session.commit()
        await session.refresh(item)
        return IngestResult(item=_to_out(item))


@router.post("/event", response_model=IngestResult)
async def post_event(body: EventIngest, _api_key: str = Depends(verify_api_key)):
    async with _db.SessionLocal() as session:
        item = await _svc.ingest_event(
            session=session,
            ticker=body.ticker,
            label=body.label,
            event_date=body.event_date,
            body=body.body,
            expires_at=body.expires_at,
        )
        await session.commit()
        await session.refresh(item)
        return IngestResult(item=_to_out(item))


@router.post("/screenshot", response_model=IngestResult)
async def post_screenshot(
    file: UploadFile = File(...),
    ticker: str = Form(...),
    note: Optional[str] = Form(None),
    hypothesis_id: Optional[str] = Form(None),
    vision_enabled: Optional[bool] = Form(None),
    expires_at: Optional[str] = Form(None),
    _api_key: str = Depends(verify_api_key),
):
    """Multipart screenshot upload. Writes the image + sidecar markdown
    into the operator's vault, optionally calls Claude vision for an
    auto-summary, and inserts a tv_context_items row.

    Returns 503 if VAULT_PATH is not configured (vault is laptop-only).
    """
    from app.tv_context import vault as _vault
    from app.tv_context import vision as _vision
    from app.core.config import SETTINGS

    if not _vault.vault_root():
        raise HTTPException(
            status_code=503,
            detail="VAULT_PATH not configured on this instance",
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="empty file")

    parsed_expiry: datetime.datetime | None = None
    if expires_at:
        try:
            parsed_expiry = datetime.datetime.fromisoformat(
                expires_at.replace("Z", "+00:00")
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid expires_at iso format")

    use_vision = (
        vision_enabled
        if vision_enabled is not None
        else SETTINGS.TV_CTX_SCREENSHOT_VISION_DEFAULT
    )

    write_result = _vault.write_screenshot(
        ticker=ticker,
        image_bytes=image_bytes,
        operator_note=note or "",
        hypothesis_id=hypothesis_id,
    )

    payload: dict = {
        "filename": write_result.image_filename,
        "note": note or "",
        "hypothesis_id": hypothesis_id,
    }
    vision_block_md: str | None = None
    if use_vision:
        vision_result = await _vision.summarize_chart(
            image_bytes=image_bytes,
            ticker=ticker,
            operator_note=note,
        )
        payload["vision"] = vision_result
        vision_block_md = vision_result.get("summary_md")

    _vault.append_vision_block(
        sidecar_path=write_result.sidecar_path,
        vision_md=vision_block_md,
    )

    async with _db.SessionLocal() as session:
        item = await _svc.ingest_screenshot_row(
            session=session,
            ticker=ticker,
            vault_path=str(write_result.sidecar_path),
            payload=payload,
            expires_at=parsed_expiry,
        )
        # Optional hypothesis link.
        if hypothesis_id:
            from app.tv_context.models import HypothesisTVContextLink

            session.add(
                HypothesisTVContextLink(
                    hypothesis_id=hypothesis_id,
                    tv_context_item_id=item.id,
                    stance="context",
                )
            )
        await session.commit()
        await session.refresh(item)
        return IngestResult(item=_to_out(item))


@router.get("/by-ticker/{ticker}", response_model=List[TVContextItemOut])
async def get_by_ticker(
    ticker: str,
    include_expired: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
    _api_key: str = Depends(verify_api_key),
):
    async with _db.SessionLocal() as session:
        rows = await _svc.list_by_ticker(
            session=session,
            ticker=ticker.upper(),
            include_expired=include_expired,
            limit=limit,
        )
        return [_to_out(r) for r in rows]


@router.get("/by-trade/{trade_id}", response_model=List[TVContextItemOut])
async def get_by_trade(
    trade_id: str, _api_key: str = Depends(verify_api_key)
):
    async with _db.SessionLocal() as session:
        rows = await _svc.list_for_trade(session=session, trade_id=trade_id)
        return [_to_out(r) for r in rows]


@router.post("/{item_id}/archive", response_model=TVContextItemOut)
async def archive_item(item_id: str, _api_key: str = Depends(verify_api_key)):
    async with _db.SessionLocal() as session:
        item = await _svc.archive_item(session=session, item_id=item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="not found")
        await session.commit()
        await session.refresh(item)
        return _to_out(item)


@router.post("/import")
async def import_item(
    payload: dict, _api_key: str = Depends(verify_api_key)
):
    """Idempotent peer-side ingest. Used by SyncOutbox kind=tv_context_*."""
    await _svc.apply_imported_item(payload)
    return {"status": "ok"}


@router.get("/vision-spend", response_model=VisionSpendOut)
async def get_vision_spend(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    _api_key: str = Depends(verify_api_key),
):
    try:
        year_s, month_s = month.split("-")
        year, month_n = int(year_s), int(month_s)
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    async with _db.SessionLocal() as session:
        total, n = await _svc.vision_spend_for_month(
            session=session, year=year, month=month_n
        )
        return VisionSpendOut(month=month, total_usd=round(total, 4), call_count=n)
