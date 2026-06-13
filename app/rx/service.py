"""rx service — recommendations read/write (finance-only)."""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional, Tuple

from sqlalchemy import desc, func, select

from app.core import db as _db
from app.core.config import SETTINGS
from app.rx.models import Recommendation


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _ensure_aware(value: Optional[_dt.datetime]) -> Optional[_dt.datetime]:
    """SQLite drops tz; coerce naive datetimes back to UTC-aware."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value


def _short_id(uuid_str: str) -> str:
    return uuid_str[:8] if uuid_str else ""


# ---- Mutations --------------------------------------------------------------

async def create(
    *,
    domain: str,
    drift_score: Optional[float] = None,
    confidence: Optional[int] = None,
    tldr: Optional[str] = None,
    body_md: Optional[str] = None,
    rx_md_path: Optional[str] = None,
    facts_json: Optional[object] = None,
    source_refs: Optional[object] = None,
    signals_fired: Optional[object] = None,
    drift_breakdown: Optional[object] = None,
    confidence_breakdown: Optional[object] = None,
    created_at: Optional[_dt.datetime] = None,
    linked_hypothesis_ids: Optional[list] = None,
) -> Recommendation:
    """Insert a recommendation. `owner_user_id` is server-side from env."""
    if domain != "finance":
        # Belt + suspenders. DB CHECK also rejects.
        raise ValueError("domain must be 'finance'")
    # Phase 2 (retrieval-depth): citation verification. Annotate each
    # source_ref with whether its quote actually appears in the cited chunk.
    # Deterministic, no LLM. Wrapped so a verifier bug can never block ingest
    # (a crash degrades to unannotated refs; a genuine mismatch is recorded).
    verified_refs = source_refs
    try:
        from app.rx import citation_check
        verified_refs = citation_check.annotate_source_refs(source_refs)
    except Exception as exc:  # noqa: BLE001
        import logging as _log
        _log.getLogger(__name__).warning(
            "rx.create: citation verification failed: %s", exc
        )

    row = Recommendation(
        owner_user_id=SETTINGS.RX_OPERATOR_UUID,
        domain=domain,
        status="open",
        drift_score=drift_score,
        confidence=confidence,
        tldr=tldr,
        body_md=body_md,
        rx_md_path=rx_md_path,
        facts_json=facts_json,
        source_refs=verified_refs,
        signals_fired=signals_fired,
        drift_breakdown=drift_breakdown,
        confidence_breakdown=confidence_breakdown,
        linked_hypothesis_ids=linked_hypothesis_ids,
        snooze_count=0,
    )
    if created_at is not None:
        # Coerce naive datetimes to UTC-aware so Postgres comparisons and
        # the rolling-window cutoff in list_recs() stay correct. Otherwise
        # a payload like "2026-05-15T10:00:00" silently lands without tz
        # and the next aware-vs-naive comparison either raises (Postgres)
        # or quietly misbehaves (SQLite).
        row.created_at = _ensure_aware(created_at)

    # Phase 2 (tv-context-decision-engine-enrichment): stamp attention
    # axis from recent TV-context inputs mentioning the rec's tickers.
    # Best-effort — a compute failure must NEVER block rec creation.
    try:
        from app.rx.tv_context_signal import compute_attention_for_rec

        att = await compute_attention_for_rec(tldr=tldr, body_md=body_md)
        row.attention_score = att.get("score") or 0.0
        row.attention_breakdown = att.get("breakdown") or {}
    except Exception as exc:  # noqa: BLE001
        import logging as _log

        _log.getLogger(__name__).warning(
            "rx.create: attention compute failed: %s", exc
        )

    async with _db.SessionLocal() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def disposition(
    rec_id: str,
    *,
    disposition: str,
    subjective_fit_1_5: Optional[int] = None,
    outcome_note: Optional[str] = None,
) -> Recommendation:
    """Apply a non-snooze disposition.

    Maps disposition → status:
      acted_as_prescribed / acted_modified → 'acted'
      skipped → 'acted' (with acted_disposition='skipped', preserves UX)
      dismissed → 'dismissed'
    """
    now = _utcnow()
    if disposition == "dismissed":
        status = "dismissed"
    elif disposition in ("acted_as_prescribed", "acted_modified", "skipped"):
        status = "acted"
    else:
        raise ValueError(f"unknown disposition: {disposition}")

    async with _db.SessionLocal() as session:
        row = await session.scalar(
            select(Recommendation).where(
                Recommendation.id == rec_id,
                Recommendation.domain == "finance",
                Recommendation.owner_user_id == SETTINGS.RX_OPERATOR_UUID,
            )
        )
        if row is None:
            raise LookupError(f"recommendation not found: {rec_id}")
        # Guard against re-dispositioning a terminal-state rec. The
        # frontend hides the panel for these, but a direct API call can
        # still overwrite `acted_at` and corrupt the audit trail.
        if row.status not in ("open", "snoozed"):
            raise ValueError(
                f"rec is in terminal state ({row.status}); "
                "cannot re-disposition"
            )
        row.status = status
        row.acted_disposition = disposition
        row.acted_at = now
        if subjective_fit_1_5 is not None:
            row.subjective_fit_1_5 = subjective_fit_1_5
        if outcome_note is not None:
            row.outcome_note = outcome_note
        await session.commit()
        await session.refresh(row)
    return row


async def snooze(rec_id: str, *, days: int) -> Recommendation:
    """Snooze a rec for N days. Increments snooze_count."""
    if not (1 <= days <= 7):
        raise ValueError("days must be in [1,7]")
    now = _utcnow()
    until = now + _dt.timedelta(days=days)
    async with _db.SessionLocal() as session:
        row = await session.scalar(
            select(Recommendation).where(
                Recommendation.id == rec_id,
                Recommendation.domain == "finance",
                Recommendation.owner_user_id == SETTINGS.RX_OPERATOR_UUID,
            )
        )
        if row is None:
            raise LookupError(f"recommendation not found: {rec_id}")
        # Terminal recs can't be snoozed back into the queue — preserves
        # the audit trail and prevents accidental double-tap on a closed
        # rec from incrementing snooze_count.
        if row.status not in ("open", "snoozed"):
            raise ValueError(
                f"rec is in terminal state ({row.status}); cannot snooze"
            )
        row.status = "snoozed"
        row.snoozed_until = until
        row.snooze_count = (row.snooze_count or 0) + 1
        await session.commit()
        await session.refresh(row)
    return row


# ---- Reads ------------------------------------------------------------------

_DEFAULT_LIST_WINDOW_DAYS = 60
_AGING_THRESHOLD_DAYS = 14
_FORCED_DECISION_SNOOZE_COUNT = 2
_TLDR_SHORT_LEN = 100


def _list_item_from_row(row: Recommendation, now: _dt.datetime) -> dict:
    created_at = _ensure_aware(row.created_at) or now
    age_days = max(0, (now - created_at).days)
    snoozed_until = _ensure_aware(row.snoozed_until)
    auto_revived = (
        row.status == "snoozed"
        and snoozed_until is not None
        and snoozed_until < now
    )
    tldr_short = (row.tldr or "")[:_TLDR_SHORT_LEN] if row.tldr else None
    return {
        "id": row.id,
        "short_id": _short_id(row.id),
        "created_at": created_at,
        "age_days": age_days,
        "drift_score": row.drift_score,
        "confidence": row.confidence,
        "status": row.status,
        "tldr_short": tldr_short,
        "acted_disposition": row.acted_disposition,
        "subjective_fit_1_5": row.subjective_fit_1_5,
        "snoozed_until": snoozed_until,
        "snooze_count": row.snooze_count or 0,
        "auto_revived": auto_revived,
        "forced_decision": (row.snooze_count or 0)
        >= _FORCED_DECISION_SNOOZE_COUNT,
        "aging": age_days > _AGING_THRESHOLD_DAYS,
        # Phase 2 (tv-context): operator-attention axis (nullable on legacy).
        "attention_score": row.attention_score,
        "attention_breakdown": row.attention_breakdown,
        # Phase 2 (retrieval-depth): citation verification status, derived
        # from the (possibly annotated) source_refs. Cheap + pure.
        "citations_status": _citations_status(row.source_refs),
    }


def _citations_status(source_refs: object) -> str:
    """Rec-level citation verification status (best-effort, never raises)."""
    try:
        from app.rx import citation_check
        return citation_check.status_from_refs(source_refs)
    except Exception:  # noqa: BLE001
        return "no_quotes"


# Status ordering for the list view: open first, snoozed next, then
# acted, then dismissed. Implemented in Python because cross-DB CASE
# WHEN syntax differs (Postgres vs SQLite quirks); we already fetch the
# full list to compute derived fields, so the cost is negligible.
_STATUS_ORDER = {"open": 1, "snoozed": 2, "acted": 3, "dismissed": 4}


async def list_recs(
    *,
    window_days: int = _DEFAULT_LIST_WINDOW_DAYS,
    limit: int = 200,
) -> List[dict]:
    """List finance recs in the rolling window.

    Defense-in-depth: filters `domain='finance'` even though CHECK
    constraint blocks INSERTs (so a misconfigured app can never leak
    cross-domain rows).
    """
    now = _utcnow()
    cutoff = now - _dt.timedelta(days=window_days)
    async with _db.SessionLocal() as session:
        result = await session.scalars(
            select(Recommendation)
            .where(
                Recommendation.domain == "finance",
                Recommendation.owner_user_id == SETTINGS.RX_OPERATOR_UUID,
                Recommendation.created_at >= cutoff,
            )
            .order_by(desc(Recommendation.created_at))
            .limit(limit)
        )
        rows = list(result)
    items = [_list_item_from_row(r, now) for r in rows]
    items.sort(
        key=lambda it: (
            _STATUS_ORDER.get(it["status"], 99),
            -int(it["created_at"].timestamp()),
        )
    )
    return items


async def get(rec_id: str) -> Optional[Recommendation]:
    async with _db.SessionLocal() as session:
        return await session.scalar(
            select(Recommendation).where(
                Recommendation.id == rec_id,
                Recommendation.domain == "finance",
                Recommendation.owner_user_id == SETTINGS.RX_OPERATOR_UUID,
            )
        )


# ---------------------------------------------------------------------------
# Cross-entity links (rx v1.x.1-b)
# ---------------------------------------------------------------------------

# Ticker regex + denylist live in `app.rx._constants` so the rx layer
# and the tv_context attention signal share a single source of truth.
# Re-exported here under the legacy name so existing internal callers
# keep working without a churn pass.
from app.rx._constants import (
    TICKER_NOISE_DENYLIST as _TICKER_NOISE_DENYLIST,
    TICKER_TOKEN_RE as _TICKER_TOKEN_RE,
)

async def links_for_rec(rec_id: str) -> dict:
    """Resolve hypotheses + trades referenced by a rec.

    Heuristic:
      * Hypotheses — title appears in (tldr || body_md), case-insensitive
        substring. Min title length 3 to avoid noise.
      * Trades — explicit FK (`trades.related_rec_id == rec.id`) UNION
        substring match on ticker.
    """
    from sqlalchemy import or_, select  # noqa: F401

    from app.hypotheses.models import Hypothesis
    from app.trades.models import Trade

    async with _db.SessionLocal() as session:
        rec = await session.get(Recommendation, rec_id)
        if rec is None or rec.domain != "finance":
            raise LookupError(f"rec not found: {rec_id}")
        haystack_parts: list[str] = []
        if rec.tldr:
            haystack_parts.append(rec.tldr.lower())
        if rec.body_md:
            haystack_parts.append(rec.body_md.lower())
        haystack = " ".join(haystack_parts)

        # Phase 4 (D2 fix): EXPLICIT linkage is primary. If the rec was
        # composed with `linked_hypothesis_ids`, those are the real links —
        # tagged `match_type="explicit"`. The substring heuristic below is
        # demoted to a fallback SUGGESTION (`match_type="substring_fallback"`)
        # and is suppressed entirely for any hypothesis already linked
        # explicitly, so a "NVDA" substring can't double-count or mislabel a
        # hypothesis the operator never intended.
        explicit_ids = set(rec.linked_hypothesis_ids or [])
        hyp_hits = []
        if explicit_ids:
            explicit_hyps = list(
                await session.scalars(
                    select(Hypothesis).where(Hypothesis.id.in_(explicit_ids))
                )
            )
            for h in explicit_hyps:
                hyp_hits.append({
                    "id": h.id,
                    "slug": h.slug,
                    "title": h.title,
                    "status": h.status,
                    "match_type": "explicit",
                })

        # Hypothesis substring match — pull all hypotheses (bounded N for a
        # single user) and filter in Python. Avoids the cross-DB ILIKE
        # quirk and lets us enforce min-length-3 cheaply. Demoted to fallback.
        hyps = list(await session.scalars(select(Hypothesis)))
        for h in hyps:
            if h.id in explicit_ids:
                continue  # already surfaced as explicit; don't double-count
            t = (h.title or "").lower()
            if len(t) >= 3 and t in haystack:
                hyp_hits.append({
                    "id": h.id,
                    "slug": h.slug,
                    "title": h.title,
                    "status": h.status,
                    "match_type": "substring_fallback",
                })

        # Trade matches — explicit FK OR ticker-substring (uppercased).
        trades = list(
            await session.scalars(
                select(Trade).where(Trade.related_rec_id == rec_id)
            )
        )
        explicit_ids = {t.id for t in trades}
        # Also pull recent trades on tickers mentioned in the haystack.
        # Two guards against false-positives:
        # 1. Common financial non-ticker tokens (USA, GDP, FOMC, etc.) are
        #    denied. The full list is conservative; operator can grow it.
        # 2. Time-bound the trade match: open trades always, or closed
        #    trades within the last 90 days. A 2-year-old closed META
        #    trade should not appear on every rec mentioning META.
        candidates = set(
            _TICKER_TOKEN_RE.findall((rec.tldr or "") + " " + (rec.body_md or ""))
        )
        tickers = candidates - _TICKER_NOISE_DENYLIST
        if tickers:
            import datetime as _dt2
            cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=90)
            extra = list(await session.scalars(
                select(Trade).where(
                    Trade.ticker.in_(tickers),
                    or_(Trade.exit_price.is_(None), Trade.entry_at >= cutoff),
                )
            ))
            for t in extra:
                if t.id not in explicit_ids:
                    trades.append(t)
                    explicit_ids.add(t.id)
        trade_hits = [{
            "id": t.id,
            "ticker": t.ticker,
            "side": t.side,
            "qty": t.qty,
            "entry_price": t.entry_price,
            "entry_at": t.entry_at,
            "realized_pnl": t.realized_pnl,
        } for t in trades]
    return {"hypotheses": hyp_hits, "trades": trade_hits}
