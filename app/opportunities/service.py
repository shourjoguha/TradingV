"""Opportunity generator + lifecycle service — Phase 3.1.

- :func:`generate_for_predictions` — run all rules over predictions made on
  a date (or all unprocessed). Insert Opportunity rows where rules fire.
  Idempotent via ``UNIQUE(source_prediction_id, rule_id)``.
- :func:`expire_stale` — sweep open opportunities past ``expires_at``.
- :func:`list_opportunities` / :func:`update_status` — read + transition.

Confidence is the historical (ticker, horizon, model) directional hit-rate
at generation time. Rule definitions live in ``rules.py``.

Expiry: ``expires_at = target_date + 1 day`` so the opportunity has a
window from when it was generated until just past its target horizon.
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accuracy.models import PredictionAccuracy
from app.accuracy.service import _fetch_baseline_close
from app.core import db as _db
from app.opportunities.models import Opportunity
from app.opportunities.rules import RuleInput, evaluate
from app.predictions.models import PredictionPoint

logger = logging.getLogger(__name__)


async def _hit_rate(
    session: AsyncSession,
    *,
    ticker: str,
    horizon_offset: int,
    model_id: str,
    last_n: int = 30,
) -> tuple[Optional[float], int]:
    """Per-pair directional hit-rate over the last_n evaluations."""
    stmt = (
        select(PredictionAccuracy.direction_correct)
        .where(
            PredictionAccuracy.ticker == ticker,
            PredictionAccuracy.horizon_offset == horizon_offset,
            PredictionAccuracy.model_id == model_id,
            PredictionAccuracy.direction_correct.is_not(None),
        )
        .order_by(PredictionAccuracy.evaluated_at.desc())
        .limit(last_n)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return None, 0
    correct = sum(1 for r in rows if r is True)
    return correct / len(rows), len(rows)


async def generate_for_predictions(
    *, since: Optional[datetime.datetime] = None, limit: int = 1000
) -> dict[str, int]:
    """Run rule engine over recent predictions; emit opportunities for hits.

    By default scans predictions whose ``created_at >= since`` (default: last
    24 hours). Idempotent — UNIQUE(prediction, rule) prevents duplicates.
    """
    if since is None:
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)

    stats = {"scanned": 0, "evaluated": 0, "created": 0, "skipped_no_baseline": 0}

    async with _db.SessionLocal() as session:
        stmt = (
            select(PredictionPoint)
            .where(PredictionPoint.created_at >= since)
            .order_by(PredictionPoint.created_at.desc())
            .limit(limit)
        )
        preds = (await session.execute(stmt)).scalars().all()
        stats["scanned"] = len(preds)

        for pp in preds:
            baseline = await _fetch_baseline_close(
                session, ticker=pp.ticker, interval=pp.interval, made_on=pp.made_on
            )
            if baseline is None or baseline <= 0:
                stats["skipped_no_baseline"] += 1
                continue

            hr, n = await _hit_rate(
                session,
                ticker=pp.ticker,
                horizon_offset=pp.horizon_offset,
                model_id=pp.model_id,
            )
            inp = RuleInput(
                ticker=pp.ticker,
                horizon_offset=pp.horizon_offset,
                predicted_close=pp.close,
                baseline_close=float(baseline),
                hit_rate=hr,
                sample_count=n,
            )
            hits = evaluate(inp)
            stats["evaluated"] += 1

            for hit in hits:
                # expires_at = target_date + 1 day (give it a buffer past the bar).
                expires = datetime.datetime.combine(
                    pp.target_date + datetime.timedelta(days=1),
                    datetime.time.min,
                    tzinfo=datetime.timezone.utc,
                )
                opp = Opportunity(
                    ticker=pp.ticker,
                    kind=hit.kind,
                    source_prediction_id=pp.id,
                    source_model_id=pp.model_id,
                    rule_id=hit.rule_id,
                    rule_label=hit.rule_label,
                    predicted_move_pct=hit.predicted_move_pct,
                    confidence=hit.confidence,
                    expires_at=expires,
                )
                session.add(opp)
                try:
                    await session.flush()
                    stats["created"] += 1
                except IntegrityError:
                    # Already exists for this (prediction, rule). Idempotent path.
                    await session.rollback()

        await session.commit()

    return stats


async def expire_stale(*, now: Optional[datetime.datetime] = None) -> int:
    """Mark open opportunities past expires_at as 'expired'. Returns count."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    n = 0
    async with _db.SessionLocal() as session:
        stmt = select(Opportunity).where(
            Opportunity.status == "open",
            Opportunity.expires_at.is_not(None),
            Opportunity.expires_at < now,
        )
        rows = (await session.execute(stmt)).scalars().all()
        for opp in rows:
            opp.status = "expired"
            n += 1
        await session.commit()
    return n


async def list_opportunities(
    *,
    status: Optional[str] = None,
    ticker: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    async with _db.SessionLocal() as session:
        stmt = select(Opportunity).order_by(Opportunity.generated_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Opportunity.status == status)
        if ticker:
            stmt = stmt.where(Opportunity.ticker == ticker.upper())
        rows = (await session.execute(stmt)).scalars().all()
        return [_serialize(r) for r in rows]


async def update_status(
    *, opportunity_id: str, status: str, dismissed_reason: Optional[str] = None
) -> Optional[dict]:
    if status not in ("acted", "dismissed", "open"):
        raise ValueError(f"invalid status: {status}")
    now = datetime.datetime.now(datetime.timezone.utc)
    async with _db.SessionLocal() as session:
        opp = await session.get(Opportunity, opportunity_id)
        if opp is None:
            return None
        opp.status = status
        if status == "acted":
            opp.acted_at = now
        elif status == "dismissed":
            opp.dismissed_at = now
            if dismissed_reason:
                opp.dismissed_reason = dismissed_reason
        await session.commit()
        return _serialize(opp)


def _serialize(o: Opportunity) -> dict:
    return {
        "id": o.id,
        "ticker": o.ticker,
        "kind": o.kind,
        "generated_at": o.generated_at.isoformat(),
        "source_prediction_id": o.source_prediction_id,
        "source_model_id": o.source_model_id,
        "rule_id": o.rule_id,
        "rule_label": o.rule_label,
        "predicted_move_pct": o.predicted_move_pct,
        "confidence": o.confidence,
        "status": o.status,
        "expires_at": o.expires_at.isoformat() if o.expires_at else None,
        "acted_at": o.acted_at.isoformat() if o.acted_at else None,
        "dismissed_at": o.dismissed_at.isoformat() if o.dismissed_at else None,
        "dismissed_reason": o.dismissed_reason,
    }
