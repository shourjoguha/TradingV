"""Phase 5 retention sweeps + cost aggregator + Retention/Costs endpoints."""
from __future__ import annotations

import datetime
import uuid

import pytest

from app.accuracy.models import DriftAlert, PredictionAccuracy
from app.admin import retention as _ret
from app.admin import costs as _costs
from app.core import db as _db
from app.research.models import ResearchQuery

HEADERS = {"X-API-Key": "test-key"}


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@pytest.mark.asyncio
async def test_sweep_prediction_accuracy_no_op_when_empty(client):
    """PredictionAccuracy has FK to prediction_points → analysis_tasks → analysis_jobs.
    Constructing the full chain in a unit test is heavy; smoke-test the empty path.
    """
    deleted = await _ret.sweep_prediction_accuracy()
    assert deleted == 0


@pytest.mark.asyncio
async def test_sweep_drift_alerts_drops_old_acked(client):
    old_acked = _utc_now() - datetime.timedelta(days=120)
    recent_acked = _utc_now() - datetime.timedelta(days=30)
    async with _db.SessionLocal() as session:
        # Old acked → deleted.
        session.add(
            DriftAlert(
                ticker="AAA",
                horizon_offset=1,
                model_id="kronos-stub",
                recent_mape=0.05,
                all_time_mape=0.02,
                ratio=2.5,
                recent_sample_count=20,
                all_time_sample_count=200,
                acknowledged_at=old_acked,
            )
        )
        # Recently acked → kept (within TTL).
        session.add(
            DriftAlert(
                ticker="BBB",
                horizon_offset=1,
                model_id="kronos-stub",
                recent_mape=0.05,
                all_time_mape=0.02,
                ratio=2.5,
                recent_sample_count=20,
                all_time_sample_count=200,
                acknowledged_at=recent_acked,
            )
        )
        # Unacked → kept forever.
        session.add(
            DriftAlert(
                ticker="CCC",
                horizon_offset=1,
                model_id="kronos-stub",
                recent_mape=0.05,
                all_time_mape=0.02,
                ratio=2.5,
                recent_sample_count=20,
                all_time_sample_count=200,
            )
        )
        await session.commit()
    deleted = await _ret.sweep_drift_alerts()
    assert deleted == 1


@pytest.mark.asyncio
async def test_sweep_research_queries_per_status_matrix(client):
    long_ago = _utc_now() - datetime.timedelta(days=200)
    recent = _utc_now() - datetime.timedelta(days=30)
    async with _db.SessionLocal() as session:
        # approved forever (kept).
        session.add(
            ResearchQuery(
                id=str(uuid.uuid4()),
                asked_at=long_ago,
                query="A",
                hypothesis_ids=[],
                status="approved",
            )
        )
        # pending forever (kept).
        session.add(
            ResearchQuery(
                id=str(uuid.uuid4()),
                asked_at=long_ago,
                query="B",
                hypothesis_ids=[],
                status="pending",
            )
        )
        # dismissed > 180d (deleted).
        session.add(
            ResearchQuery(
                id=str(uuid.uuid4()),
                asked_at=long_ago,
                query="C",
                hypothesis_ids=[],
                status="dismissed",
            )
        )
        # dismissed within 180d (kept).
        session.add(
            ResearchQuery(
                id=str(uuid.uuid4()),
                asked_at=recent,
                query="D",
                hypothesis_ids=[],
                status="dismissed",
            )
        )
        # error > 90d (deleted).
        session.add(
            ResearchQuery(
                id=str(uuid.uuid4()),
                asked_at=long_ago,
                query="E",
                hypothesis_ids=[],
                status="error",
            )
        )
        await session.commit()
    deleted = await _ret.sweep_research_queries()
    assert deleted == 2  # one dismissed > 180d + one error > 90d


@pytest.mark.asyncio
async def test_retention_endpoint_lists_classes(client):
    r = await client.get("/v1/admin/retention", headers=HEADERS)
    assert r.status_code == 200
    items = r.json()["items"]
    keys = {row["key"] for row in items}
    assert {"prediction_accuracy", "drift_alerts", "research_queries"}.issubset(keys)


@pytest.mark.asyncio
async def test_purge_endpoint_two_step(client):
    # Preview path returns no deletes.
    r = await client.post(
        "/v1/admin/retention/research_queries/purge",
        headers=HEADERS,
        json={"confirm": False},
    )
    assert r.status_code == 200
    assert r.json()["preview"] is True


@pytest.mark.asyncio
async def test_purge_endpoint_unknown_key(client):
    r = await client.post(
        "/v1/admin/retention/random/purge",
        headers=HEADERS,
        json={"confirm": True},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_costs_monthly_aggregates_research(client):
    _costs.clear_cache()
    today = _utc_now()
    async with _db.SessionLocal() as session:
        session.add(
            ResearchQuery(
                id=str(uuid.uuid4()),
                asked_at=today,
                query="cost test",
                hypothesis_ids=[],
                status="approved",
                est_cost_usd=0.42,
            )
        )
        await session.commit()
    r = await client.get("/v1/admin/costs/monthly", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["research_count"] >= 1
    assert body["research_total_usd"] >= 0.42


@pytest.mark.asyncio
async def test_costs_recent_returns_series(client):
    _costs.clear_cache()
    r = await client.get("/v1/admin/costs/recent?days=7", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 7
    assert all("date" in item for item in body["items"])


@pytest.mark.asyncio
async def test_costs_recent_caps_days(client):
    r = await client.get("/v1/admin/costs/recent?days=120", headers=HEADERS)
    assert r.status_code == 400
