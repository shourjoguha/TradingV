"""rx attention signal — derive an "operator attention" axis on a
recommendation by counting & decay-weighting recent TV-context inputs
that mention the same tickers.

Plan: tv-context-decision-engine-enrichment Phase 2.

Public surface:
  - ``DEFAULT_KIND_WEIGHTS`` — per-kind multipliers locked by the plan.
  - ``HALF_LIFE_DAYS`` — exponential decay half-life (7d).
  - ``compute_attention(ticker, since_days=14)`` — async; returns
    ``{"score": float, "breakdown": {kind: int}}`` for a single ticker.
  - ``compute_attention_for_rec(tldr, body_md, since_days=14)`` — extracts
    tickers from rec text (re-uses the rx denylist), aggregates score
    across all matched tickers, returns
    ``{"score": float, "breakdown": {ticker: {kind: count, score: float}}}``.

Design B locked (explicit attention axis on the rec object, not a
composite-score modulation). See plan §Phase 2.
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
from typing import Dict, Iterable, Optional

from sqlalchemy import select

from app.core import db as _db
from app.tv_context.models import (
    KIND_EVENT,
    KIND_IDEA,
    KIND_NOTE,
    KIND_SCREENSHOT,
    KIND_WEBHOOK,
    STATUS_ACTIVE,
    TVContextItem,
)

logger = logging.getLogger(__name__)


# ---- Locked tuning (plan §Phase 2) -----------------------------------------

DEFAULT_KIND_WEIGHTS: Dict[str, float] = {
    KIND_SCREENSHOT: 1.0,   # highest effort → highest operator-intent signal
    KIND_NOTE: 0.7,
    KIND_IDEA: 0.5,
    KIND_EVENT: 0.4,
    KIND_WEBHOOK: 0.2,      # auto-fired, low operator intent
}

HALF_LIFE_DAYS: float = 7.0
"""Weekly half-life — screenshots from a month ago barely count."""


# ---- Ticker extraction ------------------------------------------------------
#
# Regex + denylist live in `app.rx._constants` so this module + service.py +
# the frontend RxFinanceDetail TICKER_NOISE_DENYLIST stay in lockstep.
# Previous shape `from app.rx.service import _TICKER_NOISE_DENYLIST` coupled
# us to service.py's module load order — extracted 2026-05-20.

from app.rx._constants import extract_tickers as _extract  # noqa: E402


def extract_tickers(tldr: Optional[str], body_md: Optional[str]) -> list[str]:
    """Pull ALL-CAPS 2-5 letter tokens from rec text. Apply the shared
    rx denylist (AI/USA/GDP/SELL/BUY/etc). Returns uppercase deduped
    list, preserves first-seen order."""
    return _extract(tldr, body_md)


# ---- Decay math -------------------------------------------------------------


def _decay(age_days: float, half_life: float = HALF_LIFE_DAYS) -> float:
    """exp(-ln(2) * age / half_life). Stable for large age values; floors
    to 0 cleanly because exp() of large negatives underflows to ~0."""
    if age_days < 0:
        age_days = 0.0
    return math.exp(-math.log(2.0) * age_days / half_life)


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _ensure_aware(value: Optional[_dt.datetime]) -> Optional[_dt.datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value


# ---- Public surface ---------------------------------------------------------


async def compute_attention(
    ticker: str,
    *,
    since_days: int = 14,
    kind_weights: Optional[Dict[str, float]] = None,
    now: Optional[_dt.datetime] = None,
) -> dict:
    """Score recent TV-context items mentioning ``ticker``.

    Returns ``{"score": float, "breakdown": {kind: count}}``. Score is
    Σ (kind_weight × exp(-age_days × ln2 / half_life)) over every
    active item in the rolling window. Empty universe → 0.0 + all zeros.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        return {"score": 0.0, "breakdown": _zero_breakdown()}

    weights = kind_weights or DEFAULT_KIND_WEIGHTS
    anchor = now or _utcnow()
    cutoff = anchor - _dt.timedelta(days=max(0, since_days))

    async with _db.SessionLocal() as session:
        rows = list(
            await session.scalars(
                select(TVContextItem).where(
                    TVContextItem.ticker == sym,
                    TVContextItem.status == STATUS_ACTIVE,
                    TVContextItem.captured_at >= cutoff,
                )
            )
        )

    score = 0.0
    breakdown = _zero_breakdown()
    for row in rows:
        captured = _ensure_aware(row.captured_at) or anchor
        age = (anchor - captured).total_seconds() / 86400.0
        weight = weights.get(row.kind, 0.0)
        score += weight * _decay(age)
        breakdown[row.kind] = breakdown.get(row.kind, 0) + 1

    return {"score": float(score), "breakdown": breakdown}


async def compute_attention_for_rec(
    *,
    tldr: Optional[str],
    body_md: Optional[str],
    since_days: int = 14,
    kind_weights: Optional[Dict[str, float]] = None,
    now: Optional[_dt.datetime] = None,
) -> dict:
    """Aggregate attention across every ticker mentioned in a rec.

    Returns:
        ``{"score": float, "breakdown": {ticker: {kind: count, score: float}}}``

    The top-level ``score`` is the MAX across tickers (operator wants to
    see "this rec touches a name with significant attention" rather than
    "sum of unrelated attention spread across 3 names").
    """
    tickers = extract_tickers(tldr, body_md)
    breakdown: dict[str, dict] = {}
    max_score = 0.0
    for sym in tickers:
        try:
            per = await compute_attention(
                sym,
                since_days=since_days,
                kind_weights=kind_weights,
                now=now,
            )
        except Exception as exc:  # noqa: BLE001
            # Best-effort: an attention-compute failure on one ticker
            # must not prevent rec creation.
            logger.warning(
                "rx.tv_context_signal: compute failed for %s: %s", sym, exc
            )
            continue
        per_with_score = dict(per["breakdown"])
        per_with_score["score"] = per["score"]
        breakdown[sym] = per_with_score
        if per["score"] > max_score:
            max_score = per["score"]
    return {"score": float(max_score), "breakdown": breakdown}


def _zero_breakdown() -> Dict[str, int]:
    return {
        KIND_SCREENSHOT: 0,
        KIND_NOTE: 0,
        KIND_IDEA: 0,
        KIND_EVENT: 0,
        KIND_WEBHOOK: 0,
    }
