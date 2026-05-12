"""Tests for app.research.ranking — composite score, recompute, auto-age."""
from __future__ import annotations

import datetime
import uuid

import pytest

from app.research import ranking
from app.research.models import (
    STATUS_DISMISSED,
    STATUS_PENDING,
    ResearchQuery,
)
from app.hypotheses.models import (
    Hypothesis,
    HypothesisEvaluation,
    STATUS_ACTIVE,
)


HEADERS = {"X-API-Key": "test-key"}


# ---------------------------------------------------------------------------
# Pure-function score components
# ---------------------------------------------------------------------------


def test_score_has_action_boosts():
    """proposed_action present > verdict-only."""
    base = dict(
        at_risk_hyp=False,
        recent_at_risk_eval=False,
        cost_usd=0.0,
        dismiss_rate=0.0,
        age_days=0.0,
    )
    with_action = ranking._score_components(has_action=True, **base)
    without_action = ranking._score_components(has_action=False, **base)
    assert with_action > without_action
    assert with_action - without_action == ranking.W_HAS_ACTION


def test_score_at_risk_hypothesis_boosts():
    base = dict(
        has_action=False,
        recent_at_risk_eval=False,
        cost_usd=0.0,
        dismiss_rate=0.0,
        age_days=0.0,
    )
    assert (
        ranking._score_components(at_risk_hyp=True, **base)
        - ranking._score_components(at_risk_hyp=False, **base)
        == ranking.W_AT_RISK_HYP
    )


def test_score_dismiss_rate_penalty_clamps():
    """dismiss_rate above 1.0 must NOT penalise beyond -W_DISMISS_RATE."""
    base = dict(
        has_action=False,
        at_risk_hyp=False,
        recent_at_risk_eval=False,
        cost_usd=0.0,
        age_days=0.0,
    )
    bound = ranking._score_components(dismiss_rate=1.0, **base)
    over = ranking._score_components(dismiss_rate=5.0, **base)
    assert bound == pytest.approx(over)


def test_score_age_penalty_grows_with_age():
    base = dict(
        has_action=False,
        at_risk_hyp=False,
        recent_at_risk_eval=False,
        cost_usd=0.0,
        dismiss_rate=0.0,
    )
    fresh = ranking._score_components(age_days=0.0, **base)
    old = ranking._score_components(age_days=30.0, **base)
    assert fresh > old


# ---------------------------------------------------------------------------
# compute_score against the live DB
# ---------------------------------------------------------------------------


def _make_hypothesis(
    *,
    slug: str,
    days_to_expire: int = 365,
    status: str = STATUS_ACTIVE,
) -> Hypothesis:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    return Hypothesis(
        id=str(uuid.uuid4()),
        slug=slug,
        title=f"hyp {slug}",
        claim_type="directional",
        axis="macro",
        primary_metric="spx_50d_change",
        tracking_signal="VIX",
        invalidator={"op": "always_false"},
        ttl_months=12,
        expires_at=now + datetime.timedelta(days=days_to_expire),
        status=status,
    )


def _make_query(
    *,
    hyp_ids: list[str],
    asked_days_ago: float = 0.0,
    response: dict | None = None,
    cost_usd: float | None = None,
    status: str = STATUS_PENDING,
) -> ResearchQuery:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    return ResearchQuery(
        id=str(uuid.uuid4()),
        query="test query",
        hypothesis_ids=hyp_ids,
        bundle={},
        response=response,
        status=status,
        asked_at=now - datetime.timedelta(days=asked_days_ago),
        est_cost_usd=cost_usd,
    )


@pytest.mark.asyncio
async def test_at_risk_hypothesis_outranks_normal(client):
    """A query against a hypothesis expiring in 10d outranks one against a hypothesis expiring in 365d."""
    from app.core import db as _db

    async with _db.SessionLocal() as session:
        h_at_risk = _make_hypothesis(slug="at-risk-1", days_to_expire=10)
        h_safe = _make_hypothesis(slug="safe-1", days_to_expire=365)
        session.add_all([h_at_risk, h_safe])
        await session.flush()

        q_at_risk = _make_query(hyp_ids=[h_at_risk.id])
        q_safe = _make_query(hyp_ids=[h_safe.id])
        session.add_all([q_at_risk, q_safe])
        await session.flush()

        s_at_risk = await ranking.compute_score(session, q_at_risk)
        s_safe = await ranking.compute_score(session, q_safe)
        await session.commit()

        assert s_at_risk > s_safe


@pytest.mark.asyncio
async def test_proposed_action_outranks_verdict_only(client):
    from app.core import db as _db

    async with _db.SessionLocal() as session:
        h = _make_hypothesis(slug="hyp-action")
        session.add(h)
        await session.flush()

        q_action = _make_query(
            hyp_ids=[h.id],
            response={"proposed_action": {"hypothesis_slug": "hyp-action"}},
        )
        q_verdict = _make_query(hyp_ids=[h.id], response={"verdict_md": "no action"})
        session.add_all([q_action, q_verdict])
        await session.flush()

        s_a = await ranking.compute_score(session, q_action)
        s_v = await ranking.compute_score(session, q_verdict)
        await session.commit()

        assert s_a > s_v


@pytest.mark.asyncio
async def test_recent_query_outranks_old(client):
    from app.core import db as _db

    async with _db.SessionLocal() as session:
        h = _make_hypothesis(slug="hyp-age")
        session.add(h)
        await session.flush()

        q_fresh = _make_query(hyp_ids=[h.id], asked_days_ago=0.0)
        q_old = _make_query(hyp_ids=[h.id], asked_days_ago=20.0)
        session.add_all([q_fresh, q_old])
        await session.flush()

        s_fresh = await ranking.compute_score(session, q_fresh)
        s_old = await ranking.compute_score(session, q_old)
        await session.commit()

        assert s_fresh > s_old


@pytest.mark.asyncio
async def test_dismissal_rate_penalty(client):
    """A hypothesis whose past queries were 100% dismissed should rank lower for new queries on it."""
    from app.core import db as _db

    async with _db.SessionLocal() as session:
        h_trusted = _make_hypothesis(slug="trusted")
        h_dismissed = _make_hypothesis(slug="dismissy")
        session.add_all([h_trusted, h_dismissed])
        await session.flush()

        # Pre-populate decision history: 3 dismissed for h_dismissed, 3
        # approved for h_trusted.
        for _ in range(3):
            session.add(_make_query(hyp_ids=[h_dismissed.id], status=STATUS_DISMISSED))
            session.add(_make_query(hyp_ids=[h_trusted.id], status="approved"))
        await session.flush()

        q_dismissed = _make_query(hyp_ids=[h_dismissed.id])
        q_trusted = _make_query(hyp_ids=[h_trusted.id])
        session.add_all([q_dismissed, q_trusted])
        await session.flush()

        s_d = await ranking.compute_score(session, q_dismissed)
        s_t = await ranking.compute_score(session, q_trusted)
        await session.commit()

        assert s_t > s_d


# ---------------------------------------------------------------------------
# recompute_all_pending rebalances is_deferred
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recompute_marks_top_5_visible_rest_deferred(client):
    from app.core import db as _db

    async with _db.SessionLocal() as session:
        # 7 hypotheses, varying at-risk-ness so scores spread out.
        hyps = [
            _make_hypothesis(
                slug=f"h{i}",
                days_to_expire=5 if i < 5 else 365,  # first 5 are at-risk
            )
            for i in range(7)
        ]
        session.add_all(hyps)
        await session.flush()
        for h in hyps:
            session.add(_make_query(hyp_ids=[h.id]))
        await session.flush()

        count = await ranking.recompute_all_pending(session)
        await session.commit()

        assert count == 7

        # All 7 still exist; top 5 by score have is_deferred=False.
        from sqlalchemy import select

        rows = (
            await session.execute(select(ResearchQuery).where(ResearchQuery.status == STATUS_PENDING))
        ).scalars().all()
        visible = [r for r in rows if not r.is_deferred]
        deferred = [r for r in rows if r.is_deferred]
        assert len(visible) == 5
        assert len(deferred) == 2
        # The deferred ones have the lowest scores.
        max_deferred = max(r.score for r in deferred)
        min_visible = min(r.score for r in visible)
        assert min_visible >= max_deferred


# ---------------------------------------------------------------------------
# auto_age_expired
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_age_dismisses_31_day_old_pending(client):
    from app.core import db as _db

    async with _db.SessionLocal() as session:
        h = _make_hypothesis(slug="hyp-age-old")
        session.add(h)
        await session.flush()

        # 31 days old + 5 days old — only the 31d should age out at threshold=30.
        q_old = _make_query(hyp_ids=[h.id], asked_days_ago=31.0)
        q_fresh = _make_query(hyp_ids=[h.id], asked_days_ago=5.0)
        session.add_all([q_old, q_fresh])
        await session.commit()

        aged = await ranking.auto_age_expired(session, threshold_days=30)
        await session.commit()

        assert aged == 1
        await session.refresh(q_old)
        await session.refresh(q_fresh)
        assert q_old.status == STATUS_DISMISSED
        assert q_old.approved_action == {"reason": "auto-aged-out", "threshold_days": 30}
        assert q_old.auto_aged_at is not None
        assert q_fresh.status == STATUS_PENDING


@pytest.mark.asyncio
async def test_auto_age_idempotent(client):
    """A second call after the sweep should change nothing."""
    from app.core import db as _db

    async with _db.SessionLocal() as session:
        h = _make_hypothesis(slug="hyp-idempotent")
        session.add(h)
        await session.flush()
        session.add(_make_query(hyp_ids=[h.id], asked_days_ago=45.0))
        await session.commit()

        first = await ranking.auto_age_expired(session, threshold_days=30)
        await session.commit()
        second = await ranking.auto_age_expired(session, threshold_days=30)
        await session.commit()

        assert first == 1
        assert second == 0


# ---------------------------------------------------------------------------
# Endpoint: order=score & include_deferred filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queries_endpoint_order_by_score(client):
    """GET /v1/research/queries?status=pending&order=score returns top-scored first."""
    from app.core import db as _db

    async with _db.SessionLocal() as session:
        # Mixed scores: one with action + at-risk hyp (high), one verdict-only against a safe hyp (low).
        h_at_risk = _make_hypothesis(slug="ranked-hi", days_to_expire=10)
        h_safe = _make_hypothesis(slug="ranked-lo", days_to_expire=365)
        session.add_all([h_at_risk, h_safe])
        await session.flush()
        q_high = _make_query(
            hyp_ids=[h_at_risk.id],
            response={"proposed_action": {"hypothesis_slug": "ranked-hi"}},
        )
        q_low = _make_query(hyp_ids=[h_safe.id])
        session.add_all([q_high, q_low])
        await session.flush()
        await ranking.compute_score(session, q_high)
        await ranking.compute_score(session, q_low)
        await session.commit()

    r = await client.get(
        "/v1/research/queries?status=pending&order=score&limit=10",
        headers=HEADERS,
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    # High-score row first.
    assert items[0]["score"] is not None
    assert items[1]["score"] is not None
    assert items[0]["score"] > items[1]["score"]


@pytest.mark.asyncio
async def test_queries_endpoint_filters_deferred(client):
    """include_deferred=false hides backlog rows."""
    from app.core import db as _db

    async with _db.SessionLocal() as session:
        h = _make_hypothesis(slug="filter-test")
        session.add(h)
        await session.flush()
        q_visible = _make_query(hyp_ids=[h.id])
        q_deferred = _make_query(hyp_ids=[h.id])
        q_deferred.is_deferred = True
        session.add_all([q_visible, q_deferred])
        await session.commit()

    r = await client.get(
        "/v1/research/queries?status=pending&include_deferred=false&limit=10",
        headers=HEADERS,
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
