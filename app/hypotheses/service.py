"""Service layer for hypotheses — CRUD, list filters, lifespan tick.

Lifespan tick (called from ``app.main`` daily) does three steps in order:
1. TTL expiry — rows past ``expires_at`` flip to ``expired``.
2. Invalidator evaluation — DSL fires → flip to ``invalidated``.
3. Cascade — rows whose ``precondition_id`` just turned non-active flip
   to ``cancelled``. Recursive (bounded). Each transition writes a
   :class:`HypothesisEvaluation` row.
"""
from __future__ import annotations

import datetime
import logging
from typing import Iterable, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.hypotheses import invalidator as inv_dsl
from app.hypotheses.models import (
    ALL_CLAIM_TYPES,
    ALL_STATUSES,
    CLAIM_BREAKOUT,
    CLAIM_REGIME,
    CLAIM_SINGLE_NAME,
    CLAIM_TACTICAL,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_INVALIDATED,
    STATUS_MANUAL_CLOSED,
    Hypothesis,
    HypothesisEvaluation,
)
from app.hypotheses.schemas import (
    HypothesisCancel,
    HypothesisCreate,
    HypothesisPatch,
)

logger = logging.getLogger(__name__)

# Per-claim_type TTL defaults (months). Operator can override at create time.
TTL_BY_CLAIM_TYPE = {
    CLAIM_REGIME: 30,
    CLAIM_BREAKOUT: 30,
    CLAIM_TACTICAL: 6,
    CLAIM_SINGLE_NAME: 18,
}


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _expires_at(created_at: datetime.datetime, ttl_months: int) -> datetime.datetime:
    # Approximate "N months" as N*30 days. Off by ≤2 days/year — fine for
    # daily-resolution invalidator semantics, no dateutil dep needed.
    return created_at + datetime.timedelta(days=ttl_months * 30)


# ----------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------

async def create(session: AsyncSession, payload: HypothesisCreate) -> Hypothesis:
    ttl = payload.ttl_months
    if ttl is None:
        ttl = TTL_BY_CLAIM_TYPE.get(payload.claim_type, 12)
    created = _now()
    row = Hypothesis(
        slug=payload.slug,
        title=payload.title,
        claim_type=payload.claim_type,
        axis=payload.axis,
        parent_id=payload.parent_id,
        precondition_id=payload.precondition_id,
        primary_metric=payload.primary_metric,
        tracking_signal=payload.tracking_signal,
        invalidator=payload.invalidator,
        ttl_months=ttl,
        created_at=created,
        expires_at=_expires_at(created, ttl),
        status=STATUS_ACTIVE,
        body_md=payload.body_md,
    )
    session.add(row)
    await session.flush()
    return row


async def get(session: AsyncSession, hyp_id: str) -> Optional[Hypothesis]:
    return await session.get(Hypothesis, hyp_id)


async def get_by_slug(session: AsyncSession, slug: str) -> Optional[Hypothesis]:
    return (
        await session.execute(select(Hypothesis).where(Hypothesis.slug == slug))
    ).scalar_one_or_none()


async def list_(
    session: AsyncSession,
    *,
    status: Optional[str] = None,
    axis: Optional[str] = None,
    claim_type: Optional[str] = None,
) -> list[Hypothesis]:
    stmt = select(Hypothesis).order_by(Hypothesis.created_at.desc())
    if status:
        stmt = stmt.where(Hypothesis.status == status)
    if axis:
        stmt = stmt.where(Hypothesis.axis == axis)
    if claim_type:
        stmt = stmt.where(Hypothesis.claim_type == claim_type)
    return list((await session.execute(stmt)).scalars().all())


async def patch(
    session: AsyncSession, hyp: Hypothesis, payload: HypothesisPatch
) -> Hypothesis:
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(hyp, k, v)
    await session.flush()
    return hyp


async def delete(session: AsyncSession, hyp: Hypothesis) -> None:
    await session.delete(hyp)
    await session.flush()


async def cancel(
    session: AsyncSession, hyp: Hypothesis, payload: HypothesisCancel
) -> HypothesisEvaluation:
    """Operator dismissal — flips to ``manual_closed`` and records an evaluation."""
    if hyp.status != STATUS_ACTIVE:
        # Idempotent: already-closed cancels return the latest evaluation row.
        latest = await _latest_eval(session, hyp.id)
        if latest is not None:
            return latest
    before = hyp.status
    hyp.status = STATUS_MANUAL_CLOSED
    ev = HypothesisEvaluation(
        hypothesis_id=hyp.id,
        status_before=before,
        status_after=STATUS_MANUAL_CLOSED,
        reason=f"manual close: {payload.reason}",
    )
    session.add(ev)
    await session.flush()
    return ev


async def recent_evaluations(
    session: AsyncSession, hyp_id: str, *, limit: int = 10
) -> list[HypothesisEvaluation]:
    stmt = (
        select(HypothesisEvaluation)
        .where(HypothesisEvaluation.hypothesis_id == hyp_id)
        .order_by(desc(HypothesisEvaluation.evaluated_at))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _latest_eval(
    session: AsyncSession, hyp_id: str
) -> Optional[HypothesisEvaluation]:
    rows = await recent_evaluations(session, hyp_id, limit=1)
    return rows[0] if rows else None


# ----------------------------------------------------------------------
# Lifespan tick
# ----------------------------------------------------------------------

async def run_daily_tick(session: AsyncSession) -> dict[str, int]:
    """Run the daily evaluation loop. Returns a stats dict for logging.

    Steps:
      1. Expire active rows whose TTL has passed.
      2. Evaluate invalidators on the (still) active rows; flip those that fire.
      3. Cascade — rows whose precondition_id is NOT active get cancelled.
         Repeat until no further changes (bounded at 10 iterations to guard
         against circular precondition graphs).
    """
    now = _now()
    stats = {"expired": 0, "invalidated": 0, "cancelled": 0, "evaluated": 0}

    # 1. Expiry
    expired_rows = (
        await session.execute(
            select(Hypothesis).where(
                Hypothesis.status == STATUS_ACTIVE,
                Hypothesis.expires_at < now,
            )
        )
    ).scalars().all()
    for row in expired_rows:
        row.status = STATUS_EXPIRED
        session.add(
            HypothesisEvaluation(
                hypothesis_id=row.id,
                status_before=STATUS_ACTIVE,
                status_after=STATUS_EXPIRED,
                reason="ttl expired",
            )
        )
        stats["expired"] += 1

    # 2. Invalidator evaluation on remaining active rows.
    active_rows = (
        await session.execute(
            select(Hypothesis).where(Hypothesis.status == STATUS_ACTIVE)
        )
    ).scalars().all()
    for row in active_rows:
        try:
            result = await inv_dsl.evaluate(
                row.invalidator, session=session, hypothesis_id=row.id
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "invalidator failed for hypothesis %s: %s", row.slug, exc
            )
            continue
        stats["evaluated"] += 1
        if result.fired:
            row.status = STATUS_INVALIDATED
            session.add(
                HypothesisEvaluation(
                    hypothesis_id=row.id,
                    status_before=STATUS_ACTIVE,
                    status_after=STATUS_INVALIDATED,
                    reason=f"invalidator fired: {result.reason}",
                    invalidator_result=result.to_dict(),
                )
            )
            stats["invalidated"] += 1

    await session.flush()

    # 3. Cascade. Iterate until no changes (max 10 to break cycles).
    for _ in range(10):
        # Find active rows whose precondition_id points to a non-active row.
        changed = await _cascade_pass(session)
        if not changed:
            break
        stats["cancelled"] += changed
    await session.flush()
    return stats


async def _cascade_pass(session: AsyncSession) -> int:
    """One iteration of cascade. Returns count of rows cancelled."""
    # Pull active rows with a precondition_id set; check parent status.
    active_with_pre = (
        await session.execute(
            select(Hypothesis).where(
                Hypothesis.status == STATUS_ACTIVE,
                Hypothesis.precondition_id.is_not(None),
            )
        )
    ).scalars().all()
    if not active_with_pre:
        return 0
    pre_ids = {r.precondition_id for r in active_with_pre}
    pre_rows = {
        p.id: p
        for p in (
            await session.execute(
                select(Hypothesis).where(Hypothesis.id.in_(pre_ids))
            )
        ).scalars().all()
    }
    n = 0
    for child in active_with_pre:
        parent = pre_rows.get(child.precondition_id)
        if parent is None:
            continue
        if parent.status not in (STATUS_ACTIVE,):
            child.status = STATUS_CANCELLED
            session.add(
                HypothesisEvaluation(
                    hypothesis_id=child.id,
                    status_before=STATUS_ACTIVE,
                    status_after=STATUS_CANCELLED,
                    reason=f"cascade: precondition {parent.slug} → {parent.status}",
                )
            )
            n += 1
    if n > 0:
        await session.flush()
    return n


# ----------------------------------------------------------------------
# Sidebar widget summary
# ----------------------------------------------------------------------

async def summary(session: AsyncSession) -> dict[str, int]:
    """At-a-glance counts for the sidebar widget. Cheap aggregate."""
    rows = list_  # alias
    out = {s: 0 for s in ALL_STATUSES}
    for r in await rows(session):
        out[r.status] = out.get(r.status, 0) + 1
    # "at_risk" = active rows whose expires_at is within 30 days of now.
    soon = _now() + datetime.timedelta(days=30)
    at_risk = (
        await session.execute(
            select(Hypothesis).where(
                Hypothesis.status == STATUS_ACTIVE,
                Hypothesis.expires_at < soon,
            )
        )
    ).scalars().all()
    out["at_risk"] = len(at_risk)
    return out


# ---------------------------------------------------------------------------
# Health view (rx v1.x.1-b)
# ---------------------------------------------------------------------------

async def list_health(*, limit: int = 200) -> list[dict]:
    """List hypotheses with rec-link counts for the rx finance panel.

    Returns: list of dicts ready for HypothesisHealthItem.

    Limitations:
      * No explicit FK from recommendations → hypothesis. We use a
        case-insensitive substring match on (tldr || body_md) vs the
        hypothesis title. False positives possible on common substrings;
        false negatives possible when the rec uses a different framing.
      * Only counts recs created in the last 30d (operator's working
        window — older recs aren't actionable).
    """
    import datetime as _dt
    from sqlalchemy import select, func

    from app.core import db as _db
    from app.hypotheses.models import Hypothesis
    from app.rx.models import Recommendation

    now = _dt.datetime.now(_dt.timezone.utc)
    recent_cutoff = now - _dt.timedelta(days=30)

    async with _db.SessionLocal() as session:
        hyps = list(
            await session.scalars(
                select(Hypothesis)
                .order_by(Hypothesis.expires_at)
                .limit(limit)
            )
        )
        # Pre-fetch recent finance recs once; substring-match in Python.
        # Pulling tldr+body_md for ~N<200 rows is cheap and avoids a per-
        # hypothesis correlated subquery that's awkward to express
        # cross-DB (Postgres ILIKE vs SQLite LIKE+NOCASE).
        recs = list(
            await session.scalars(
                select(Recommendation).where(
                    Recommendation.domain == "finance",
                    Recommendation.created_at >= recent_cutoff,
                )
            )
        )

    rec_text: list[str] = []
    for rec in recs:
        parts = []
        if rec.tldr:
            parts.append(rec.tldr.lower())
        if rec.body_md:
            parts.append(rec.body_md.lower())
        rec_text.append(" ".join(parts))

    out: list[dict] = []
    for h in hyps:
        created_at = h.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=_dt.timezone.utc)
        expires_at = h.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=_dt.timezone.utc)
        age_days = max(0, (now - created_at).days) if created_at else 0
        days_to_expiry = int((expires_at - now).days) if expires_at else 0
        needle = (h.title or "").lower()
        related = 0
        if needle and len(needle) >= 3:
            related = sum(1 for t in rec_text if needle in t)
        out.append({
            "id": h.id,
            "slug": h.slug,
            "title": h.title,
            "status": h.status,
            "claim_type": h.claim_type,
            "age_days": age_days,
            "days_to_expiry": days_to_expiry,
            "related_recs_count": related,
        })
    return out
