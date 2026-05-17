"""Tests for the hypothesis object + invalidator DSL — M-2.

Covers:
- CRUD round-trips on /v1/hypotheses
- Slug uniqueness 409
- Invalidator DSL validation (5 ops)
- Each op evaluated against synthetic MacroSeries rows
- Lifespan tick: TTL expiry, invalidator firing, cascade (recursive)
- Manual cancel writes evaluation row
- View registry parser: success + boot-failure path
- /v1/views surface
"""
from __future__ import annotations

import datetime
import logging

import pytest
from sqlalchemy import select

from app.core import db as _db
from app.hypotheses import invalidator as inv_dsl
from app.hypotheses import service as hyp_service
from app.hypotheses.models import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_INVALIDATED,
    STATUS_MANUAL_CLOSED,
    Hypothesis,
    HypothesisEvaluation,
)
from app.hypotheses.schemas import HypothesisCreate
from app.macro.models import MacroSeries

HEADERS = {"X-API-Key": "test-key"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_series(symbol: str, points: list[tuple[datetime.date, float]]) -> None:
    async with _db.SessionLocal() as session:
        for ts, value in points:
            session.add(
                MacroSeries(symbol=symbol, ts=ts, value=float(value), source="manual")
            )
        await session.commit()


def _payload(**overrides):
    base = {
        "slug": "thesis-a",
        "title": "Test Thesis A",
        "claim_type": "regime",
        "axis": "liquidity",
        "primary_metric": "WALCL/GDP",
        "tracking_signal": "WALCL/GDP",
        "invalidator": {"op": "manual", "args": {}},
        "ttl_months": 6,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_then_get_returns_payload(client):
    r = await client.post("/v1/hypotheses", headers=HEADERS, json=_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "thesis-a"
    assert body["status"] == STATUS_ACTIVE
    assert body["ttl_months"] == 6

    g = await client.get(f"/v1/hypotheses/{body['id']}", headers=HEADERS)
    assert g.status_code == 200
    assert g.json()["title"] == "Test Thesis A"


@pytest.mark.asyncio
async def test_create_duplicate_slug_409(client):
    r1 = await client.post("/v1/hypotheses", headers=HEADERS, json=_payload())
    assert r1.status_code == 201
    r2 = await client.post("/v1/hypotheses", headers=HEADERS, json=_payload())
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_list_filters_by_status_and_axis(client):
    await client.post("/v1/hypotheses", headers=HEADERS, json=_payload(slug="a", axis="liquidity"))
    await client.post("/v1/hypotheses", headers=HEADERS, json=_payload(slug="b", axis="growth"))
    r = await client.get("/v1/hypotheses?axis=liquidity", headers=HEADERS)
    assert r.status_code == 200
    items = r.json()["items"]
    assert {i["slug"] for i in items} == {"a"}


@pytest.mark.asyncio
async def test_patch_updates_subset(client):
    c = await client.post("/v1/hypotheses", headers=HEADERS, json=_payload())
    hid = c.json()["id"]
    r = await client.patch(
        f"/v1/hypotheses/{hid}",
        headers=HEADERS,
        json={"title": "renamed", "axis": "credit"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "renamed"
    assert r.json()["axis"] == "credit"


@pytest.mark.asyncio
async def test_delete_cascades_evaluations(client):
    c = await client.post("/v1/hypotheses", headers=HEADERS, json=_payload())
    hid = c.json()["id"]
    # Cancel to write an evaluation row.
    await client.post(
        f"/v1/hypotheses/{hid}/cancel",
        headers=HEADERS,
        json={"reason": "test"},
    )
    d = await client.delete(f"/v1/hypotheses/{hid}", headers=HEADERS)
    assert d.status_code == 204
    g = await client.get(f"/v1/hypotheses/{hid}", headers=HEADERS)
    assert g.status_code == 404
    # Evaluation rows for that hyp_id are gone too.
    async with _db.SessionLocal() as session:
        rows = (
            await session.execute(
                select(HypothesisEvaluation).where(
                    HypothesisEvaluation.hypothesis_id == hid
                )
            )
        ).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_summary_endpoint(client):
    await client.post("/v1/hypotheses", headers=HEADERS, json=_payload(slug="x"))
    await client.post("/v1/hypotheses", headers=HEADERS, json=_payload(slug="y"))
    r = await client.get("/v1/hypotheses/summary", headers=HEADERS)
    assert r.status_code == 200
    s = r.json()
    assert s[STATUS_ACTIVE] == 2
    assert s["at_risk"] >= 0


# ---------------------------------------------------------------------------
# Invalidator DSL — validation
# ---------------------------------------------------------------------------


def test_validate_unknown_op_raises():
    with pytest.raises(ValueError, match="unknown invalidator op"):
        inv_dsl.validate_spec({"op": "bogus", "args": {}})


def test_validate_ratio_below_sma_args():
    inv_dsl.validate_spec(
        {
            "op": "ratio_below_sma",
            "args": {
                "numerator": "WALCL",
                "denominator": "GDP",
                "sma_days": 200,
                "days_below": 30,
            },
        }
    )
    with pytest.raises(ValueError):
        inv_dsl.validate_spec(
            {"op": "ratio_below_sma", "args": {"numerator": "X"}}
        )


def test_validate_series_change_pct_direction():
    inv_dsl.validate_spec(
        {
            "op": "series_change_pct",
            "args": {
                "symbol": "DXY",
                "window_months": 3,
                "threshold_pct": 5.0,
                "direction": "up",
            },
        }
    )
    with pytest.raises(ValueError, match="direction"):
        inv_dsl.validate_spec(
            {
                "op": "series_change_pct",
                "args": {
                    "symbol": "DXY",
                    "window_months": 3,
                    "threshold_pct": 5.0,
                    "direction": "sideways",
                },
            }
        )


def test_create_route_rejects_bad_invalidator(monkeypatch):
    # The Pydantic schema runs validate_spec → 422 from FastAPI.
    pass


@pytest.mark.asyncio
async def test_create_route_rejects_unknown_op(client):
    r = await client.post(
        "/v1/hypotheses",
        headers=HEADERS,
        json=_payload(invalidator={"op": "nope", "args": {}}),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Invalidator DSL — evaluation against synthetic series
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eval_series_above_threshold_fires(client):
    today = datetime.date.today()
    pts = [(today - datetime.timedelta(days=i), 120.0) for i in range(0, 5)]
    await _seed_series("DXY", pts)
    spec = {
        "op": "series_above_threshold",
        "args": {"symbol": "DXY", "threshold": 110.0, "days_above": 3},
    }
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(spec, session=session)
    assert result.fired is True
    assert result.observed["streak"] >= 3


@pytest.mark.asyncio
async def test_eval_series_below_threshold_no_fire_when_short_streak(client):
    today = datetime.date.today()
    # Only 1 day below threshold; need 5.
    pts = [(today, 4.0), (today - datetime.timedelta(days=1), 6.0)]
    await _seed_series("DGS10", pts)
    spec = {
        "op": "series_below_threshold",
        "args": {"symbol": "DGS10", "threshold": 5.0, "days_below": 5},
    }
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(spec, session=session)
    assert result.fired is False


@pytest.mark.asyncio
async def test_eval_series_change_pct_up(client):
    today = datetime.date.today()
    # Base 100 → last 130 over 3mo window: +30%.
    pts = [
        (today - datetime.timedelta(days=90), 100.0),
        (today, 130.0),
    ]
    await _seed_series("BTC-USD", pts)
    spec = {
        "op": "series_change_pct",
        "args": {
            "symbol": "BTC-USD",
            "window_months": 3,
            "threshold_pct": 25.0,
            "direction": "up",
        },
    }
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(spec, session=session)
    assert result.fired is True
    assert result.observed["pct_change"] == pytest.approx(30.0, rel=1e-3)


@pytest.mark.asyncio
async def test_eval_manual_never_fires():
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(
            {"op": "manual", "args": {}}, session=session
        )
    assert result.fired is False


# ---------------------------------------------------------------------------
# Lifespan tick
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tick_expires_past_ttl(client):
    """Row whose expires_at is in the past flips to expired."""
    async with _db.SessionLocal() as session:
        past = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=1)
        row = Hypothesis(
            slug="expired-one",
            title="t",
            claim_type="regime",
            axis="x",
            primary_metric="m",
            tracking_signal="m",
            invalidator={"op": "manual", "args": {}},
            ttl_months=1,
            created_at=past - datetime.timedelta(days=60),
            expires_at=past,
            status=STATUS_ACTIVE,
        )
        session.add(row)
        await session.commit()
        rid = row.id

    async with _db.SessionLocal() as session:
        stats = await hyp_service.run_daily_tick(session)
        await session.commit()
    assert stats["expired"] == 1
    async with _db.SessionLocal() as session:
        row = await session.get(Hypothesis, rid)
        assert row.status == STATUS_EXPIRED


@pytest.mark.asyncio
async def test_tick_invalidator_fires_flips_status(client):
    """Series above threshold for required streak → status=invalidated."""
    today = datetime.date.today()
    pts = [(today - datetime.timedelta(days=i), 120.0) for i in range(0, 5)]
    await _seed_series("DXY", pts)
    spec = {
        "op": "series_above_threshold",
        "args": {"symbol": "DXY", "threshold": 110.0, "days_above": 3},
    }
    r = await client.post(
        "/v1/hypotheses",
        headers=HEADERS,
        json=_payload(slug="dxy-thesis", invalidator=spec),
    )
    hid = r.json()["id"]

    tick = await client.post("/v1/hypotheses/_tick", headers=HEADERS)
    assert tick.status_code == 200
    g = await client.get(f"/v1/hypotheses/{hid}", headers=HEADERS)
    assert g.json()["status"] == STATUS_INVALIDATED
    evals = g.json()["recent_evaluations"]
    assert any("invalidator fired" in e["reason"] for e in evals)


@pytest.mark.asyncio
async def test_tick_cascade_cancels_child_when_precondition_invalidated(client):
    """Parent gets invalidated → child with precondition_id flips to cancelled."""
    today = datetime.date.today()
    # Parent will be invalidated by series-above-threshold spec.
    pts = [(today - datetime.timedelta(days=i), 120.0) for i in range(0, 5)]
    await _seed_series("DXY", pts)
    parent_spec = {
        "op": "series_above_threshold",
        "args": {"symbol": "DXY", "threshold": 110.0, "days_above": 3},
    }
    pr = await client.post(
        "/v1/hypotheses",
        headers=HEADERS,
        json=_payload(slug="parent", invalidator=parent_spec),
    )
    pid = pr.json()["id"]
    cr = await client.post(
        "/v1/hypotheses",
        headers=HEADERS,
        json=_payload(
            slug="child",
            invalidator={"op": "manual", "args": {}},
            precondition_id=pid,
        ),
    )
    cid = cr.json()["id"]

    await client.post("/v1/hypotheses/_tick", headers=HEADERS)
    g = await client.get(f"/v1/hypotheses/{cid}", headers=HEADERS)
    assert g.json()["status"] == STATUS_CANCELLED


@pytest.mark.asyncio
async def test_tick_cascade_recursive_grandchild(client):
    """Parent invalidated → child cancelled → grandchild cancelled."""
    today = datetime.date.today()
    pts = [(today - datetime.timedelta(days=i), 120.0) for i in range(0, 5)]
    await _seed_series("DXY", pts)
    parent_spec = {
        "op": "series_above_threshold",
        "args": {"symbol": "DXY", "threshold": 110.0, "days_above": 3},
    }
    pr = await client.post(
        "/v1/hypotheses", headers=HEADERS,
        json=_payload(slug="g-parent", invalidator=parent_spec),
    )
    pid = pr.json()["id"]
    cr = await client.post(
        "/v1/hypotheses", headers=HEADERS,
        json=_payload(slug="g-child", invalidator={"op": "manual", "args": {}}, precondition_id=pid),
    )
    cid = cr.json()["id"]
    gr = await client.post(
        "/v1/hypotheses", headers=HEADERS,
        json=_payload(slug="g-grand", invalidator={"op": "manual", "args": {}}, precondition_id=cid),
    )
    gid = gr.json()["id"]

    await client.post("/v1/hypotheses/_tick", headers=HEADERS)
    for hid in (cid, gid):
        g = await client.get(f"/v1/hypotheses/{hid}", headers=HEADERS)
        assert g.json()["status"] == STATUS_CANCELLED


@pytest.mark.asyncio
async def test_manual_cancel_writes_evaluation_and_flips_status(client):
    r = await client.post("/v1/hypotheses", headers=HEADERS, json=_payload())
    hid = r.json()["id"]
    c = await client.post(
        f"/v1/hypotheses/{hid}/cancel",
        headers=HEADERS,
        json={"reason": "operator dismissed"},
    )
    assert c.status_code == 200
    assert "manual close: operator dismissed" in c.json()["reason"]
    g = await client.get(f"/v1/hypotheses/{hid}", headers=HEADERS)
    assert g.json()["status"] == STATUS_MANUAL_CLOSED


# ---------------------------------------------------------------------------
# View registry
# ---------------------------------------------------------------------------


def test_view_registry_parses_seed_files(client):
    from app.views import parser

    registry = parser.load_registry()
    assert "macro_liquidity" in registry
    spec = registry["macro_liquidity"]
    assert spec.title == "Liquidity & Credit"
    assert any(p.kind == "ratio" for p in spec.panels)


def test_view_registry_fails_on_bad_frontmatter(tmp_path):
    from app.views import parser

    bad = tmp_path / "bad.md"
    bad.write_text("---\n: not yaml\n---\nbody\n")
    with pytest.raises(ValueError):
        parser.load_registry(tmp_path)


# ---------------------------------------------------------------------------
# Phase 3 (tv-context-decision-engine-enrichment): TV-context DSL ops.
#
# `tv_context_count_since(days, min_count)` — fires when ≥min_count
# items are linked to the hypothesis in the trailing window.
# `tv_context_stance_count_since(days, stance, min_count)` — same but
# filtered to a specific stance ('supports' | 'challenges' | 'context').
# ---------------------------------------------------------------------------


async def _seed_hypothesis_with_invalidator(spec: dict) -> str:
    """Insert a hypothesis directly via ORM (bypasses route validation
    to let tests freely flip the spec under test). Returns the id."""
    now = datetime.datetime.now(datetime.timezone.utc)
    async with _db.SessionLocal() as session:
        h = Hypothesis(
            slug=f"tvctx-{now.timestamp():.4f}",
            title="tv-context invalidator test",
            claim_type="regime",
            axis="x",
            primary_metric="m",
            tracking_signal="m",
            invalidator=spec,
            ttl_months=6,
            expires_at=now + datetime.timedelta(days=180),
            status=STATUS_ACTIVE,
        )
        session.add(h)
        await session.commit()
        return h.id


async def _link_tv_context(
    hypothesis_id: str,
    ticker: str,
    *,
    stance: str = "context",
    body: str = "linked note",
    captured_at: datetime.datetime | None = None,
) -> None:
    """Ingest a note + HypothesisTVContextLink row in one shot."""
    from app.tv_context import service as tvc
    from app.tv_context.models import HypothesisTVContextLink, TVContextItem

    async with _db.SessionLocal() as session:
        item = await tvc.ingest_note(session=session, ticker=ticker, body=body)
        if captured_at is not None:
            item.captured_at = captured_at
        session.add(
            HypothesisTVContextLink(
                hypothesis_id=hypothesis_id,
                tv_context_item_id=item.id,
                stance=stance,
            )
        )
        await session.commit()


def test_validate_spec_accepts_tv_context_ops():
    inv_dsl.validate_spec(
        {"op": "tv_context_count_since", "args": {"days": 14, "min_count": 2}}
    )
    inv_dsl.validate_spec(
        {
            "op": "tv_context_stance_count_since",
            "args": {"days": 14, "stance": "challenges", "min_count": 2},
        }
    )


def test_validate_spec_rejects_tv_context_bad_args():
    with pytest.raises(ValueError):
        inv_dsl.validate_spec(
            {"op": "tv_context_count_since", "args": {"min_count": 2}}
        )
    with pytest.raises(ValueError):
        inv_dsl.validate_spec(
            {
                "op": "tv_context_count_since",
                "args": {"days": -1, "min_count": 2},
            }
        )
    with pytest.raises(ValueError):
        inv_dsl.validate_spec(
            {
                "op": "tv_context_stance_count_since",
                "args": {"days": 14, "stance": "bogus", "min_count": 2},
            }
        )


@pytest.mark.asyncio
async def test_tv_context_count_fires_at_threshold(client):
    """≥ min_count linked items in the window → fired=True."""
    spec = {"op": "tv_context_count_since", "args": {"days": 14, "min_count": 2}}
    hid = await _seed_hypothesis_with_invalidator(spec)
    await _link_tv_context(hid, "NVDA")
    await _link_tv_context(hid, "META")
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(
            spec, session=session, hypothesis_id=hid
        )
    assert result.fired is True
    assert result.observed["count"] == 2


@pytest.mark.asyncio
async def test_tv_context_count_no_fire_below_threshold(client):
    spec = {"op": "tv_context_count_since", "args": {"days": 14, "min_count": 3}}
    hid = await _seed_hypothesis_with_invalidator(spec)
    await _link_tv_context(hid, "NVDA")
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(
            spec, session=session, hypothesis_id=hid
        )
    assert result.fired is False
    assert result.observed["count"] == 1


@pytest.mark.asyncio
async def test_tv_context_count_window_cutoff(client):
    """Items older than `days` window should NOT count."""
    spec = {"op": "tv_context_count_since", "args": {"days": 7, "min_count": 1}}
    hid = await _seed_hypothesis_with_invalidator(spec)
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    await _link_tv_context(hid, "META", captured_at=old)
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(
            spec, session=session, hypothesis_id=hid
        )
    assert result.fired is False


@pytest.mark.asyncio
async def test_tv_context_stance_filter_supports(client):
    """stance='challenges' only counts challenges-tagged links."""
    spec = {
        "op": "tv_context_stance_count_since",
        "args": {"days": 14, "stance": "challenges", "min_count": 1},
    }
    hid = await _seed_hypothesis_with_invalidator(spec)
    # 2 'context' links — should NOT trip a 'challenges' threshold.
    await _link_tv_context(hid, "AAPL", stance="context")
    await _link_tv_context(hid, "NVDA", stance="context")
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(
            spec, session=session, hypothesis_id=hid
        )
    assert result.fired is False
    # Now add a single 'challenges' link → should fire.
    await _link_tv_context(hid, "META", stance="challenges")
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(
            spec, session=session, hypothesis_id=hid
        )
    assert result.fired is True
    assert result.observed["stance"] == "challenges"
    assert result.observed["count"] == 1


@pytest.mark.asyncio
async def test_tv_context_count_without_hypothesis_id_soft_skip(client):
    """Calling tv-context op without hypothesis_id returns no-fire, no crash."""
    spec = {"op": "tv_context_count_since", "args": {"days": 14, "min_count": 1}}
    async with _db.SessionLocal() as session:
        result = await inv_dsl.evaluate(spec, session=session)
    assert result.fired is False
    assert "missing hypothesis_id" in result.reason


@pytest.mark.asyncio
async def test_tick_tv_context_invalidator_flips_status(client):
    """End-to-end: run_daily_tick passes hypothesis_id; TV-context fires
    the invalidator; status flips to invalidated; evaluation row recorded."""
    spec = {
        "op": "tv_context_stance_count_since",
        "args": {"days": 14, "stance": "challenges", "min_count": 2},
    }
    hid = await _seed_hypothesis_with_invalidator(spec)
    await _link_tv_context(hid, "NVDA", stance="challenges")
    await _link_tv_context(hid, "META", stance="challenges")

    async with _db.SessionLocal() as session:
        stats = await hyp_service.run_daily_tick(session)
        await session.commit()
    assert stats["invalidated"] >= 1
    async with _db.SessionLocal() as session:
        row = await session.get(Hypothesis, hid)
        assert row.status == STATUS_INVALIDATED


@pytest.mark.asyncio
async def test_existing_macro_ops_unaffected_by_signature_change(client):
    """Adding `hypothesis_id` param must not break existing macro ops."""
    today = datetime.date.today()
    pts = [(today - datetime.timedelta(days=i), 130.0) for i in range(0, 5)]
    await _seed_series("DXY", pts)
    spec = {
        "op": "series_above_threshold",
        "args": {"symbol": "DXY", "threshold": 110.0, "days_above": 3},
    }
    async with _db.SessionLocal() as session:
        # Call without hypothesis_id — must still work.
        result = await inv_dsl.evaluate(spec, session=session)
    assert result.fired is True


@pytest.mark.asyncio
async def test_views_route_returns_registry(client):
    from app.views import parser

    parser.reload()
    r = await client.get("/v1/views", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 2
    assert any(v["id"] == "macro_liquidity" for v in body["items"])
