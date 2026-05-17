"""TV-context service: ingest + dedupe + retention + retrieval."""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
from typing import Any, Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.core.config import SETTINGS
from app.tv_context.models import (
    ALL_KINDS,
    HypothesisTVContextLink,
    KIND_EVENT,
    KIND_IDEA,
    KIND_NOTE,
    KIND_SCREENSHOT,
    KIND_WEBHOOK,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_EXPIRED,
    TVContextItem,
)

logger = logging.getLogger(__name__)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _retention_days(kind: str) -> int:
    return {
        KIND_WEBHOOK: SETTINGS.TV_CTX_RETENTION_WEBHOOK_DAYS,
        KIND_SCREENSHOT: SETTINGS.TV_CTX_RETENTION_SCREENSHOT_DAYS,
        KIND_NOTE: SETTINGS.TV_CTX_RETENTION_NOTE_DAYS,
        KIND_IDEA: SETTINGS.TV_CTX_RETENTION_IDEA_DAYS,
        KIND_EVENT: SETTINGS.TV_CTX_RETENTION_EVENT_POST_DAYS,
    }[kind]


def _default_expires_at(kind: str, captured_at: datetime.datetime) -> datetime.datetime:
    days = _retention_days(kind)
    return captured_at + datetime.timedelta(days=days)


def _normalize_payload(payload: dict[str, Any]) -> str:
    """Stable JSON for dedupe-keying. Sort keys recursively, drop counter."""
    cleaned = {k: v for k, v in payload.items() if k not in ("dedupe_count",)}
    return json.dumps(cleaned, sort_keys=True, default=str, separators=(",", ":"))


def _dedupe_key(ticker: str | None, alert_type: str, payload: dict[str, Any]) -> str:
    raw = f"{ticker or ''}|{alert_type}|{_normalize_payload(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Ticker-review parity (Phase 1 — tv-context-decision-engine-enrichment)
#
# Mirrors the video-pipeline pattern: when an operator submits a TV-context
# input with a ticker NOT in the operator's universe (roster ∪ boards ∪
# The Street tier-1/2), enqueue it to `ticker_review_queue` so it surfaces on
# Today's review strip. Webhook ingest is intentionally skipped (the alert
# rule already pre-filters the ticker — false-positive risk).
#
# Best-effort: a queue write must NEVER block / fail the host ingest.
# ---------------------------------------------------------------------------


async def _maybe_enqueue_review(
    *,
    ticker: str | None,
    kind: str,
    snippet: str | None,
) -> None:
    """Enqueue unknown ticker to review queue. Best-effort, never raises.

    Lazy imports keep cold-start fast and let tests stub the call site by
    patching ``app.tv_context.service._enqueue_review_sync``.
    """
    if not ticker:
        return
    if not getattr(SETTINGS, "TV_CTX_TICKER_REVIEW_ENABLED", True):
        return
    sym = ticker.strip().upper()
    if not sym:
        return
    try:
        from tools.vault_indexer.ingest.chart_extractor import (
            load_ticker_whitelist,
        )
        from app.ticker_review import service as _tr_svc

        whitelist = await load_ticker_whitelist()
        if sym in whitelist:
            return
        await _tr_svc.enqueue_or_bump(
            ticker=sym,
            video_id="",
            channel=f"tv_context_{kind}",
            snippet=(snippet or "").strip()[:200],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "tv_context: ticker_review enqueue failed for %s/%s: %s",
            ticker,
            kind,
            exc,
        )


def _review_snippet_from_payload(kind: str, payload: dict[str, Any]) -> str:
    """Build a short snippet for the review-queue entry (cap 200 chars)."""
    if not payload:
        return ""
    if kind == KIND_NOTE:
        return (payload.get("body") or "")
    if kind == KIND_IDEA:
        return payload.get("summary") or payload.get("url") or ""
    if kind == KIND_SCREENSHOT:
        # Prefer operator caption; fall back to vision summary.
        cap = payload.get("note") or payload.get("caption") or ""
        if cap:
            return cap
        vision = payload.get("vision") or {}
        return vision.get("summary_md") or ""
    if kind == KIND_EVENT:
        label = payload.get("label") or ""
        body = payload.get("body") or ""
        return f"{label}: {body}" if body else label
    return ""


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


async def _enqueue_outbox(kind: str, item: TVContextItem) -> None:
    """Replicate to peer via existing sync outbox (skipped for screenshots)."""
    if item.kind == KIND_SCREENSHOT:
        return
    try:
        from app.sync import service as _sync_service

        await _sync_service.enqueue_kind(
            f"tv_context_{item.kind}",
            {
                "id": item.id,
                "kind": item.kind,
                "ticker": item.ticker,
                "source": item.source,
                "captured_at": item.captured_at.isoformat()
                if item.captured_at
                else None,
                "expires_at": item.expires_at.isoformat() if item.expires_at else None,
                "payload": item.payload,
                "vault_path": item.vault_path,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("tv_context: outbox enqueue failed: %s", e)


async def ingest_webhook(
    *,
    session: AsyncSession,
    ticker: str,
    alert_type: str,
    payload_json: dict[str, Any],
    source: str = "tradingview",
    expires_at: datetime.datetime | None = None,
) -> tuple[TVContextItem, bool]:
    """Insert a webhook tv_context_item with rolling-window dedupe.

    Returns (item, deduped). When ``deduped`` is True the returned item is
    the *existing* row (with dedupe_count incremented), no new row inserted,
    no outbox enqueued.
    """
    captured_at = _now()
    payload = {
        "alert_type": alert_type,
        "data": payload_json,
        "dedupe_count": 1,
    }
    dedupe_key = _dedupe_key(ticker, alert_type, payload_json)
    window = datetime.timedelta(seconds=SETTINGS.TV_CTX_WEBHOOK_DEDUPE_WINDOW_SEC)
    cutoff = captured_at - window

    existing = await session.execute(
        select(TVContextItem)
        .where(TVContextItem.dedupe_key == dedupe_key)
        .where(TVContextItem.captured_at >= cutoff)
        .where(TVContextItem.status == STATUS_ACTIVE)
        .order_by(TVContextItem.captured_at.desc())
        .limit(1)
    )
    dupe = existing.scalar_one_or_none()
    if dupe is not None:
        existing_payload = dict(dupe.payload or {})
        existing_payload["dedupe_count"] = int(existing_payload.get("dedupe_count", 1)) + 1
        dupe.payload = existing_payload
        dupe.updated_at = captured_at
        return dupe, True

    item = TVContextItem(
        kind=KIND_WEBHOOK,
        ticker=ticker,
        source=source,
        captured_at=captured_at,
        expires_at=expires_at or _default_expires_at(KIND_WEBHOOK, captured_at),
        status=STATUS_ACTIVE,
        payload=payload,
        dedupe_key=dedupe_key,
        created_at=captured_at,
        updated_at=captured_at,
    )
    session.add(item)
    await session.flush()
    await _enqueue_outbox(KIND_WEBHOOK, item)
    return item, False


async def ingest_note(
    *,
    session: AsyncSession,
    ticker: str | None,
    body: str,
    tags: list[str] | None = None,
    expires_at: datetime.datetime | None = None,
) -> TVContextItem:
    captured_at = _now()
    item = TVContextItem(
        kind=KIND_NOTE,
        ticker=ticker,
        source="tradingview",
        captured_at=captured_at,
        expires_at=expires_at or _default_expires_at(KIND_NOTE, captured_at),
        status=STATUS_ACTIVE,
        payload={"body": body, "tags": list(tags or [])},
        created_at=captured_at,
        updated_at=captured_at,
    )
    session.add(item)
    await session.flush()
    await _enqueue_outbox(KIND_NOTE, item)
    await _maybe_enqueue_review(
        ticker=ticker, kind=KIND_NOTE, snippet=body,
    )
    return item


async def ingest_idea(
    *,
    session: AsyncSession,
    ticker: str | None,
    url: str,
    summary: str | None = None,
    tags: list[str] | None = None,
    expires_at: datetime.datetime | None = None,
) -> TVContextItem:
    captured_at = _now()
    item = TVContextItem(
        kind=KIND_IDEA,
        ticker=ticker,
        source="tradingview",
        captured_at=captured_at,
        expires_at=expires_at or _default_expires_at(KIND_IDEA, captured_at),
        status=STATUS_ACTIVE,
        payload={"url": url, "summary": summary, "tags": list(tags or [])},
        created_at=captured_at,
        updated_at=captured_at,
    )
    session.add(item)
    await session.flush()
    await _enqueue_outbox(KIND_IDEA, item)
    await _maybe_enqueue_review(
        ticker=ticker,
        kind=KIND_IDEA,
        snippet=summary or url,
    )
    return item


async def ingest_event(
    *,
    session: AsyncSession,
    ticker: str | None,
    label: str,
    event_date: datetime.date,
    body: str | None = None,
    expires_at: datetime.datetime | None = None,
) -> TVContextItem:
    captured_at = _now()
    # Events expire `event_date + N days` UNLESS operator overrides.
    if expires_at is None:
        end_of_event = datetime.datetime.combine(
            event_date, datetime.time(0, 0, tzinfo=datetime.timezone.utc)
        )
        expires_at = end_of_event + datetime.timedelta(
            days=SETTINGS.TV_CTX_RETENTION_EVENT_POST_DAYS
        )
    item = TVContextItem(
        kind=KIND_EVENT,
        ticker=ticker,
        source="tradingview",
        captured_at=captured_at,
        expires_at=expires_at,
        status=STATUS_ACTIVE,
        payload={
            "label": label,
            "event_date": event_date.isoformat(),
            "body": body,
        },
        created_at=captured_at,
        updated_at=captured_at,
    )
    session.add(item)
    await session.flush()
    await _enqueue_outbox(KIND_EVENT, item)
    await _maybe_enqueue_review(
        ticker=ticker,
        kind=KIND_EVENT,
        snippet=f"{label}: {body}" if body else label,
    )
    return item


async def ingest_screenshot_row(
    *,
    session: AsyncSession,
    ticker: str,
    vault_path: str,
    payload: dict[str, Any],
    expires_at: datetime.datetime | None = None,
) -> TVContextItem:
    """Insert the row half of a screenshot ingest.

    The file-write half (image + sidecar markdown) is the route's
    responsibility — vault paths are environment-specific.
    """
    captured_at = _now()
    item = TVContextItem(
        kind=KIND_SCREENSHOT,
        ticker=ticker,
        source="tradingview",
        captured_at=captured_at,
        expires_at=expires_at or _default_expires_at(KIND_SCREENSHOT, captured_at),
        status=STATUS_ACTIVE,
        payload=payload,
        vault_path=vault_path,
        created_at=captured_at,
        updated_at=captured_at,
    )
    session.add(item)
    await session.flush()
    # Screenshots intentionally NOT replicated via outbox (vault path
    # differs per machine; binary file lives outside DB).
    await _maybe_enqueue_review(
        ticker=ticker,
        kind=KIND_SCREENSHOT,
        snippet=_review_snippet_from_payload(KIND_SCREENSHOT, payload),
    )
    return item


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


async def recent_for_ticker(
    *,
    session: AsyncSession,
    ticker: str,
    since: datetime.datetime | None = None,
    kinds: Iterable[str] | None = None,
    limit: int = 50,
) -> list[TVContextItem]:
    stmt = (
        select(TVContextItem)
        .where(TVContextItem.ticker == ticker)
        .where(TVContextItem.status == STATUS_ACTIVE)
        .order_by(TVContextItem.captured_at.desc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(TVContextItem.captured_at >= since)
    if kinds:
        stmt = stmt.where(TVContextItem.kind.in_(list(kinds)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_by_ticker(
    *,
    session: AsyncSession,
    ticker: str,
    include_expired: bool = False,
    limit: int = 200,
) -> list[TVContextItem]:
    stmt = (
        select(TVContextItem)
        .where(TVContextItem.ticker == ticker)
        .order_by(TVContextItem.captured_at.desc())
        .limit(limit)
    )
    if not include_expired:
        stmt = stmt.where(TVContextItem.status == STATUS_ACTIVE)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(
    *, session: AsyncSession, item_id: str
) -> TVContextItem | None:
    return await session.get(TVContextItem, item_id)


# ---------------------------------------------------------------------------
# Retention sweep
# ---------------------------------------------------------------------------


def _build_tombstone(item: TVContextItem) -> dict[str, Any]:
    """Compose minimal tombstone from the item's payload before heavy fields drop."""
    payload = item.payload or {}
    summary_parts: list[str] = [f"{item.kind} on {item.ticker or 'n/a'}"]
    if item.kind == KIND_WEBHOOK:
        summary_parts.append(payload.get("alert_type", ""))
    elif item.kind == KIND_NOTE:
        body = (payload.get("body") or "").strip().splitlines()
        if body:
            summary_parts.append(body[0][:200])
    elif item.kind == KIND_IDEA:
        if payload.get("summary"):
            summary_parts.append(str(payload["summary"])[:200])
        elif payload.get("url"):
            summary_parts.append(payload["url"])
    elif item.kind == KIND_EVENT:
        summary_parts.append(payload.get("label", ""))

    tombstone: dict[str, Any] = {
        "summary": " — ".join(p for p in summary_parts if p),
        "captured_at": item.captured_at.isoformat() if item.captured_at else None,
        "expired_at": _now().isoformat(),
        "kind": item.kind,
        "ticker": item.ticker,
    }
    # Preserve vision summary verbatim if present.
    vision = (payload.get("vision") or {}) if isinstance(payload, dict) else {}
    if vision.get("summary_md"):
        tombstone["vision_summary"] = vision["summary_md"]
    if item.vault_path:
        tombstone["recreate_hint"] = item.vault_path
    return tombstone


async def expire_sweep(
    *,
    session: AsyncSession,
    now: datetime.datetime | None = None,
    file_unlink: bool = True,
) -> dict[str, int]:
    """Flip past-expiration rows to status=expired, drop heavy payload,
    write tombstone. Idempotent: rows already expired are skipped.

    For screenshots, when ``file_unlink`` is True we delete the binary at
    ``vault_path`` (sibling .png) but keep the sidecar .md. Tests pass
    ``file_unlink=False`` to avoid touching disk.

    Returns ``{"expired": N}``.
    """
    cutoff = now or _now()
    stmt = (
        select(TVContextItem)
        .where(TVContextItem.status == STATUS_ACTIVE)
        .where(TVContextItem.expires_at.is_not(None))
        .where(TVContextItem.expires_at <= cutoff)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    n = 0
    for item in rows:
        item.tombstone = _build_tombstone(item)
        item.status = STATUS_EXPIRED
        item.updated_at = cutoff
        # Drop heavy payload fields. Keep dedupe_count + structural keys.
        if item.kind == KIND_SCREENSHOT and file_unlink:
            await _unlink_screenshot(item)
        item.payload = _drop_heavy(item.payload, item.kind)
        item.heavy_blob_dropped = True
        n += 1

    return {"expired": n}


def _drop_heavy(payload: dict[str, Any] | None, kind: str) -> dict[str, Any]:
    if not payload:
        return {}
    keep: dict[str, Any] = {}
    if kind == KIND_WEBHOOK:
        keep["alert_type"] = payload.get("alert_type")
        keep["dedupe_count"] = payload.get("dedupe_count", 1)
    elif kind == KIND_NOTE:
        body = payload.get("body") or ""
        keep["preview"] = body[:200]
        keep["tags"] = payload.get("tags", [])
    elif kind == KIND_IDEA:
        keep["url"] = payload.get("url")
        keep["summary"] = (payload.get("summary") or "")[:300]
        keep["tags"] = payload.get("tags", [])
    elif kind == KIND_EVENT:
        keep["label"] = payload.get("label")
        keep["event_date"] = payload.get("event_date")
    elif kind == KIND_SCREENSHOT:
        keep["caption"] = (payload.get("note") or "")[:200]
        # Vision summary survives in tombstone, not in payload.
    return keep


async def _unlink_screenshot(item: TVContextItem) -> None:
    """Delete the .png binary; leave the sidecar .md in place.

    The sidecar will be touched by the route layer to add an "expired"
    banner — done at file-write time, not here, to keep service layer
    pure. (Phase 2 routes handle banner.)
    """
    import os
    from pathlib import Path

    vp = item.vault_path
    if not vp:
        return
    sidecar = Path(vp)
    # Sidecar is the .md; image is sibling .png with same stem.
    if sidecar.suffix.lower() != ".md":
        return
    image = sidecar.with_suffix(".png")
    try:
        if image.exists():
            os.unlink(image)
    except OSError as e:  # pragma: no cover - defensive
        logger.warning("tv_context: failed to unlink %s: %s", image, e)


# ---------------------------------------------------------------------------
# Manual archive
# ---------------------------------------------------------------------------


async def archive_item(
    *, session: AsyncSession, item_id: str, file_unlink: bool = True
) -> TVContextItem | None:
    item = await session.get(TVContextItem, item_id)
    if item is None:
        return None
    if item.status == STATUS_ARCHIVED:
        return item
    item.tombstone = _build_tombstone(item)
    if item.kind == KIND_SCREENSHOT and file_unlink:
        await _unlink_screenshot(item)
    item.payload = _drop_heavy(item.payload, item.kind)
    item.heavy_blob_dropped = True
    item.status = STATUS_ARCHIVED
    item.updated_at = _now()
    return item


# ---------------------------------------------------------------------------
# Sync apply (peer-side ingest)
# ---------------------------------------------------------------------------


async def apply_imported_item(payload: dict[str, Any]) -> None:
    """Idempotent peer-side ingest. Re-uses ``id`` from origin so duplicate
    pushes are no-ops."""
    item_id = payload.get("id")
    if not item_id:
        return
    async with _db.SessionLocal() as session:
        existing = await session.get(TVContextItem, item_id)
        if existing is not None:
            return
        captured_at = _parse_dt(payload.get("captured_at"))
        expires_at = _parse_dt(payload.get("expires_at"))
        item = TVContextItem(
            id=item_id,
            kind=payload.get("kind") or KIND_NOTE,
            ticker=payload.get("ticker"),
            source=payload.get("source") or "tradingview",
            captured_at=captured_at or _now(),
            expires_at=expires_at,
            status=STATUS_ACTIVE,
            payload=payload.get("payload") or {},
            vault_path=payload.get("vault_path"),
            created_at=captured_at or _now(),
            updated_at=_now(),
        )
        session.add(item)
        await session.commit()


def _parse_dt(value: Any) -> datetime.datetime | None:
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Lifespan loop
# ---------------------------------------------------------------------------


async def expire_loop(*, stop_event=None, interval_seconds: int = 3600) -> None:
    import asyncio

    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            async with _db.SessionLocal() as session:
                stats = await expire_sweep(session=session)
                if stats["expired"]:
                    logger.info("tv_context: expired %d items", stats["expired"])
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("tv_context: expire sweep crashed; retrying next tick")
        try:
            if stop_event is not None:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                if stop_event.is_set():
                    return
            else:
                await asyncio.sleep(interval_seconds)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise


# ---------------------------------------------------------------------------
# Trade-close enrichment (Phase 5)
# ---------------------------------------------------------------------------


async def enrich_on_trade_close(
    *,
    session: AsyncSession,
    trade_id: str,
    ticker: str,
    entry_at: datetime.datetime,
    exit_at: datetime.datetime,
    realized_pnl: float | None,
    window_hours: int = 24,
) -> dict[str, int]:
    """Walk tv_context_items captured around the trade-entry window; stamp
    them with ``tombstone.related_trade_id`` + outcome, append item-id to
    ``trades.context_refs``.

    Returns ``{"linked": N}``.
    """
    from app.trades.models import Trade

    window = datetime.timedelta(hours=window_hours)
    lo, hi = entry_at - window, entry_at + window
    stmt = (
        select(TVContextItem)
        .where(TVContextItem.ticker == ticker)
        .where(TVContextItem.captured_at >= lo)
        .where(TVContextItem.captured_at <= hi)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    pnl_outcome: dict[str, Any] = {
        "trade_id": trade_id,
        "pnl": realized_pnl,
        "win": (realized_pnl or 0) > 0 if realized_pnl is not None else None,
        "closed_at": exit_at.isoformat() if exit_at else None,
    }

    linked = 0
    for item in items:
        tomb = dict(item.tombstone or {})
        trades_list = list(tomb.get("trades") or [])
        if not any(t.get("trade_id") == trade_id for t in trades_list):
            trades_list.append(pnl_outcome)
            tomb["trades"] = trades_list
            item.tombstone = tomb
            item.updated_at = _now()
            linked += 1

    if linked:
        trade = await session.get(Trade, trade_id)
        if trade is not None:
            refs = list(trade.context_refs or [])
            for it in items:
                if it.id not in refs:
                    refs.append(it.id)
            trade.context_refs = refs

    return {"linked": linked}


async def list_for_trade(
    *, session: AsyncSession, trade_id: str
) -> list[TVContextItem]:
    """Return every tv_context_item referenced by a trade.context_refs."""
    from app.trades.models import Trade

    trade = await session.get(Trade, trade_id)
    if trade is None or not trade.context_refs:
        return []
    refs = list(trade.context_refs)
    if not refs:
        return []
    stmt = (
        select(TVContextItem)
        .where(TVContextItem.id.in_(refs))
        .order_by(TVContextItem.captured_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Cost aggregation (Phase 6)
# ---------------------------------------------------------------------------


async def vision_spend_for_month(
    *, session: AsyncSession, year: int, month: int
) -> tuple[float, int]:
    """Sum payload.vision.cost_usd across rows captured in given month.

    Tombstone rows preserve `vision_summary` but not `cost_usd` (heavy is
    dropped at expiry). Active + expired rows scanned via JSON path; SQLite
    parity requires Python-side aggregation.
    """
    start = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    if month == 12:
        end = datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
    else:
        end = datetime.datetime(year, month + 1, 1, tzinfo=datetime.timezone.utc)

    stmt = (
        select(TVContextItem)
        .where(TVContextItem.kind == KIND_SCREENSHOT)
        .where(TVContextItem.captured_at >= start)
        .where(TVContextItem.captured_at < end)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())
    total = 0.0
    n = 0
    for item in items:
        vision = (item.payload or {}).get("vision") or {}
        cost = vision.get("cost_usd")
        if isinstance(cost, (int, float)):
            total += float(cost)
            n += 1
    return total, n
