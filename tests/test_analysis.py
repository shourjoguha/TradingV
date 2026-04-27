"""Analysis service + route tests.

Under the Tier-1 queue, ``POST /v1/analysis/run`` returns 202 + a
``queue_id`` and the worker drains async. These tests focus on the
service layer (``submit_run``) directly to keep assertions immediate.
The HTTP queue surface is exercised in ``tests/test_queue.py``.
"""
from __future__ import annotations

import pytest

from app.analysis import service

HEADERS = {"X-API-Key": "test-key"}


@pytest.mark.asyncio
async def test_submit_run_creates_job_and_tasks(client):
    job = await service.submit_run(
        tickers=["AAPL"], intervals=["1d"], model_ids=["kronos_base"]
    )
    assert job.task_count == 1
    assert job.status == "done"

    # Ticker auto-registered via the route surface.
    tr = await client.get("/v1/tickers/AAPL", headers=HEADERS)
    assert tr.status_code == 200

    # Empty OHLCV cache → insufficient history → ineligible.
    jr = await client.get(f"/v1/analysis/jobs/{job.id}", headers=HEADERS)
    assert jr.status_code == 200
    body = jr.json()
    assert body["status"] == "done"
    assert len(body["tasks"]) == 1
    t = body["tasks"][0]
    assert t["status"] == "ineligible"
    assert t["ineligible_reason"] == "INSUFFICIENT_HISTORY"


@pytest.mark.asyncio
async def test_submit_run_fan_out(client):
    job = await service.submit_run(
        tickers=["AAPL", "MSFT"],
        intervals=["1d", "5m"],
        model_ids=["kronos_base", "kronos_small"],
    )
    # 2 × 2 × 2 = 8.
    assert job.task_count == 8


@pytest.mark.asyncio
async def test_submit_run_default_expands_all_models(client):
    job = await service.submit_run(tickers=["AAPL"], intervals=["1d"])
    # 1 × 1 × N registered models.
    assert job.task_count >= 1


@pytest.mark.asyncio
async def test_submit_run_rejects_unknown_model(client):
    """Route still returns 400 for invalid input — pre-validates before
    enqueueing so user gets immediate feedback."""
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["1d"], "model_ids": ["kronos_vapor"]},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_submit_run_rejects_bad_interval(client):
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["17m"]},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_unsupported_interval_surfaces_as_ineligible_task(client):
    # 1m is canonical for intervals but not in any Kronos model's
    # supported_intervals. Validator rejects per task with
    # UNSUPPORTED_INTERVAL.
    job = await service.submit_run(
        tickers=["AAPL"], intervals=["1m"], model_ids=["kronos_base"]
    )
    jr = await client.get(f"/v1/analysis/jobs/{job.id}", headers=HEADERS)
    t = jr.json()["tasks"][0]
    assert t["status"] == "ineligible"
    assert t["ineligible_reason"] == "UNSUPPORTED_INTERVAL"


@pytest.mark.asyncio
async def test_list_jobs_returns_summaries(client):
    # Submit two runs through the service layer (skip the queue async dance).
    for _ in range(2):
        await service.submit_run(
            tickers=["AAPL"], intervals=["1d"], model_ids=["kronos_base"]
        )
    r = await client.get("/v1/analysis/jobs", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    # Newest first.
    assert body[0]["submitted_at"] >= body[1]["submitted_at"]
    # Summary shape — no tasks embedded.
    assert "tasks" not in body[0]
    assert body[0]["task_count"] == 1


@pytest.mark.asyncio
async def test_get_job_404(client):
    r = await client.get("/v1/analysis/jobs/does-not-exist", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_submit_run_requires_api_key(client):
    r = await client.post(
        "/v1/analysis/run",
        json={"tickers": ["AAPL"], "intervals": ["1d"]},
    )
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_debug_stub_path_returns_synthetic_forecast(client, monkeypatch):
    """When DEBUG_STUB=true AND enough bars exist, adapter returns a result."""
    from app.core.config import SETTINGS

    # Seed cache with >=600 bars for kronos_base on 1d/AAPL.
    import datetime

    from app.core import db as _db
    from app.market_data.models import OhlcvBar

    monkeypatch.setattr(SETTINGS, "DEBUG_STUB", True)

    from app.market_data.providers.base import Bar
    from app.market_data.service import _upsert_bars

    base_ts = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    bars = [
        Bar(
            ts=base_ts + datetime.timedelta(days=i),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
            amount=1.0,
        )
        for i in range(600)
    ]
    async with _db.SessionLocal() as session:
        await _upsert_bars(session, "AAPL", "1d", "test", bars)
        await session.commit()

    job = await service.submit_run(
        tickers=["AAPL"], intervals=["1d"], model_ids=["kronos_base"]
    )

    jr = await client.get(f"/v1/analysis/jobs/{job.id}", headers=HEADERS)
    t = jr.json()["tasks"][0]
    assert t["status"] == "done", t
    assert t["result_json"]["model_id"] == "kronos_base"
    assert len(t["result_json"]["forecast"]) > 0
    assert t["result_json"]["meta"]["stub"] is True
