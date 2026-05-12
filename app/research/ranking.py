"""Composite-score ranking for research_queries.

The Today landing surfaces only the top 5 pending queries by `score`,
ranked over quality rather than recency. The rest stay pending but are
flagged `is_deferred=True` so the landing UI hides them. Idle pending
queries auto-dismiss after 30 days via the retention loop.

The score is a weighted sum:

  score = 1.0 * has_action
        + 0.8 * at_risk_hyp
        + 0.6 * recent_at_risk_eval
        + 0.4 * log1p(cost_usd)
        - 0.5 * dismiss_rate
        - 0.05 * age_days

Bigger = more attention-worthy. Verdict-only (no proposed_action), an
operator who dismisses this hypothesis's queries often, and age all
demote the score.

Recompute paths:
  - On query creation (`compute_score` called by service.ask after persist)
  - Nightly via retention loop (`recompute_all_pending`)
  - Auto-dismiss expired (`auto_age_expired`) — also called by retention

Single source of truth. Frontend does no ranking math.
"""
from __future__ import annotations

import datetime
import math
from typing import Iterable

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.hypotheses.models import (
    Hypothesis,
    HypothesisEvaluation,
    STATUS_ACTIVE,
)
from app.research.models import (
    STATUS_DISMISSED,
    STATUS_PENDING,
    ResearchQuery,
)


# Tunables — keep narrow + visible. Edits here are the single touchpoint
# for ranking-formula iteration.
W_HAS_ACTION = 1.0
W_AT_RISK_HYP = 0.8
W_RECENT_AT_RISK_EVAL = 0.6
W_COST = 0.4
W_DISMISS_RATE = 0.5
W_AGE = 0.05

# Hypothesis is "at risk" if it expires within this window.
AT_RISK_TTL_DAYS = 30

# A hypothesis evaluation counts as recently-at-risk if it landed in this
# trailing window AND its status_after is at-risk-flavoured.
RECENT_EVAL_WINDOW_DAYS = 14
AT_RISK_EVAL_STATUSES = {"at_risk", "near_invalidated"}

# Top-N visible on Today; rest get is_deferred=True.
TOP_N_VISIBLE = 5

# Pending queries idle this many days get auto-dismissed.
DEFAULT_AUTO_AGE_DAYS = 30


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _as_aware(value: datetime.datetime | None) -> datetime.datetime | None:
    """Postgres TIMESTAMPTZ returns aware; SQLite returns naive. Normalise."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def _score_components(
    *,
    has_action: bool,
    at_risk_hyp: bool,
    recent_at_risk_eval: bool,
    cost_usd: float,
    dismiss_rate: float,
    age_days: float,
) -> float:
    """Pure function — easy to unit test in isolation."""
    return (
        W_HAS_ACTION * (1.0 if has_action else 0.0)
        + W_AT_RISK_HYP * (1.0 if at_risk_hyp else 0.0)
        + W_RECENT_AT_RISK_EVAL * (1.0 if recent_at_risk_eval else 0.0)
        + W_COST * math.log1p(max(cost_usd, 0.0))
        - W_DISMISS_RATE * max(min(dismiss_rate, 1.0), 0.0)
        - W_AGE * max(age_days, 0.0)
    )


async def _hypothesis_lookup(
    session: AsyncSession, hypothesis_ids: list[str]
) -> dict[str, Hypothesis]:
    if not hypothesis_ids:
        return {}
    stmt = select(Hypothesis).where(Hypothesis.id.in_(hypothesis_ids))
    rows = (await session.execute(stmt)).scalars().all()
    return {h.id: h for h in rows}


async def _recent_at_risk_eval_set(
    session: AsyncSession,
    hypothesis_ids: list[str],
    now: datetime.datetime,
) -> set[str]:
    """Hypothesis IDs with an at-risk-flavour evaluation in the trailing window."""
    if not hypothesis_ids:
        return set()
    cutoff = now - datetime.timedelta(days=RECENT_EVAL_WINDOW_DAYS)
    stmt = (
        select(HypothesisEvaluation.hypothesis_id)
        .where(HypothesisEvaluation.hypothesis_id.in_(hypothesis_ids))
        .where(HypothesisEvaluation.evaluated_at >= cutoff)
        .where(HypothesisEvaluation.status_after.in_(list(AT_RISK_EVAL_STATUSES)))
        .distinct()
    )
    rows = (await session.execute(stmt)).scalars().all()
    return set(rows)


async def _dismiss_rate_by_hypothesis(
    session: AsyncSession, hypothesis_ids: list[str]
) -> dict[str, float]:
    """For each hypothesis, return (dismissed_count / total_decided_count).

    Decided = approved + dismissed (excludes pending + error). Returns 0.0
    when there's no decision history, so virgin hypotheses don't get
    penalised.
    """
    if not hypothesis_ids:
        return {}
    # Pull all decided rows for these hypotheses; small enough to compute
    # client-side. Approximation: we don't try to attribute partial
    # hypothesis credit on multi-hyp queries.
    stmt = select(
        ResearchQuery.hypothesis_ids,
        ResearchQuery.status,
    ).where(ResearchQuery.status.in_([STATUS_DISMISSED, "approved"]))
    rows = (await session.execute(stmt)).all()
    totals: dict[str, list[int]] = {hid: [0, 0] for hid in hypothesis_ids}  # [dismissed, total]
    target_set = set(hypothesis_ids)
    for hyp_ids, status in rows:
        if not hyp_ids:
            continue
        # hypothesis_ids stored as JSON list of strings.
        for hid in hyp_ids:
            if hid not in target_set:
                continue
            totals[hid][1] += 1
            if status == STATUS_DISMISSED:
                totals[hid][0] += 1
    return {
        hid: (d / t if t > 0 else 0.0)
        for hid, (d, t) in totals.items()
    }


async def compute_score(
    session: AsyncSession, query: ResearchQuery, now: datetime.datetime | None = None
) -> float:
    """Compute and ASSIGN the composite score on a single query.

    Does not commit. Caller is responsible for session.commit().
    """
    now = now or _utcnow()
    hyp_ids: list[str] = list(query.hypothesis_ids or [])

    hyp_lookup = await _hypothesis_lookup(session, hyp_ids)
    at_risk_hyp = any(
        h.status == STATUS_ACTIVE
        and _as_aware(h.expires_at) is not None
        and _as_aware(h.expires_at) <= now + datetime.timedelta(days=AT_RISK_TTL_DAYS)
        for h in hyp_lookup.values()
    )

    recent_eval_set = await _recent_at_risk_eval_set(session, hyp_ids, now)
    recent_at_risk_eval = any(hid in recent_eval_set for hid in hyp_ids)

    dismiss_rates = await _dismiss_rate_by_hypothesis(session, hyp_ids)
    # Use the MAX dismiss-rate across the query's hypotheses — penalise
    # the most-dismissed one. Avoids letting a single trusted hypothesis
    # drag the rate down on a multi-hyp query.
    dismiss_rate = max((dismiss_rates.get(hid, 0.0) for hid in hyp_ids), default=0.0)

    cost_usd = float(query.est_cost_usd or 0.0)

    asked_at = _as_aware(query.asked_at) or now
    age_days = max((now - asked_at).total_seconds() / 86400.0, 0.0)

    has_action = bool(
        query.response
        and isinstance(query.response, dict)
        and query.response.get("proposed_action")
    )

    score = _score_components(
        has_action=has_action,
        at_risk_hyp=at_risk_hyp,
        recent_at_risk_eval=recent_at_risk_eval,
        cost_usd=cost_usd,
        dismiss_rate=dismiss_rate,
        age_days=age_days,
    )
    query.score = score
    return score


async def recompute_all_pending(
    session: AsyncSession, now: datetime.datetime | None = None
) -> int:
    """Recompute score for every pending query + rebalance is_deferred.

    Returns the count of queries rescored. After this runs, the top
    TOP_N_VISIBLE pending queries (by score DESC) have is_deferred=False;
    the rest have is_deferred=True.
    """
    now = now or _utcnow()
    stmt = select(ResearchQuery).where(ResearchQuery.status == STATUS_PENDING)
    rows = (await session.execute(stmt)).scalars().all()
    for q in rows:
        await compute_score(session, q, now=now)

    # Rebalance is_deferred. Sort by score DESC, NULLs last; top N visible.
    rows_sorted = sorted(
        rows,
        key=lambda q: (q.score if q.score is not None else float("-inf")),
        reverse=True,
    )
    for i, q in enumerate(rows_sorted):
        q.is_deferred = i >= TOP_N_VISIBLE

    return len(rows)


async def auto_age_expired(
    session: AsyncSession,
    threshold_days: int = DEFAULT_AUTO_AGE_DAYS,
    now: datetime.datetime | None = None,
) -> int:
    """Auto-dismiss pending queries older than threshold_days.

    Sets:
      - status = 'dismissed'
      - approved_at = now
      - approved_action = {'reason': 'auto-aged-out', 'threshold_days': N}
      - auto_aged_at = now

    Returns the count of rows updated. Idempotent — a second call sweeps
    only newly-expired rows.
    """
    now = now or _utcnow()
    cutoff = now - datetime.timedelta(days=threshold_days)
    stmt = (
        update(ResearchQuery)
        .where(ResearchQuery.status == STATUS_PENDING)
        .where(ResearchQuery.asked_at < cutoff)
        .values(
            status=STATUS_DISMISSED,
            approved_at=now,
            approved_action={
                "reason": "auto-aged-out",
                "threshold_days": threshold_days,
            },
            auto_aged_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    return result.rowcount or 0


def is_deferred_visible(query: ResearchQuery) -> bool:
    """Convenience: true if this query should appear on Today's pending panel."""
    return query.status == STATUS_PENDING and not query.is_deferred
