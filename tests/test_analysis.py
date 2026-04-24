from __future__ import annotations

import pytest

HEADERS = {"X-API-Key": "test-key"}


@pytest.mark.asyncio
async def test_submit_run_creates_job_and_tasks(client):
    # Ticker not yet registered — service should auto-upsert it.
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["1d"], "model_ids": ["kronos_base"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task_count"] == 1
    assert body["status"] == "done"
    job_id = body["job_id"]

    # Ticker auto-registered.
    tr = await client.get("/v1/tickers/AAPL", headers=HEADERS)
    assert tr.status_code == 200

    # Empty OHLCV cache → insufficient history → ineligible.
    jr = await client.get(f"/v1/analysis/jobs/{job_id}", headers=HEADERS)
    assert jr.status_code == 200
    job = jr.json()
    assert job["status"] == "done"
    assert len(job["tasks"]) == 1
    t = job["tasks"][0]
    assert t["status"] == "ineligible"
    assert t["ineligible_reason"] == "INSUFFICIENT_HISTORY"


@pytest.mark.asyncio
async def test_submit_run_fan_out(client):
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={
            "tickers": ["AAPL", "MSFT"],
            "intervals": ["1d", "5m"],
            "model_ids": ["kronos_base", "kronos_small"],
        },
    )
    assert r.status_code == 200
    # 2 tickers × 2 intervals × 2 models = 8.
    assert r.json()["task_count"] == 8


@pytest.mark.asyncio
async def test_submit_run_default_expands_all_models(client):
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["1d"]},
    )
    assert r.status_code == 200
    # 1 × 1 × 3 registered models.
    assert r.json()["task_count"] == 3


@pytest.mark.asyncio
async def test_submit_run_rejects_unknown_model(client):
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
    # supported_intervals. Request parse accepts (canonical); validator
    # rejects with UNSUPPORTED_INTERVAL per task.
    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["1m"], "model_ids": ["kronos_base"]},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    jr = await client.get(f"/v1/analysis/jobs/{job_id}", headers=HEADERS)
    t = jr.json()["tasks"][0]
    assert t["status"] == "ineligible"
    assert t["ineligible_reason"] == "UNSUPPORTED_INTERVAL"


@pytest.mark.asyncio
async def test_list_jobs_returns_summaries(client):
    # Submit two runs, then list.
    for _ in range(2):
        r = await client.post(
            "/v1/analysis/run",
            headers=HEADERS,
            json={"tickers": ["AAPL"], "intervals": ["1d"], "model_ids": ["kronos_base"]},
        )
        assert r.status_code == 200
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

    r = await client.post(
        "/v1/analysis/run",
        headers=HEADERS,
        json={"tickers": ["AAPL"], "intervals": ["1d"], "model_ids": ["kronos_base"]},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    jr = await client.get(f"/v1/analysis/jobs/{job_id}", headers=HEADERS)
    t = jr.json()["tasks"][0]
    assert t["status"] == "done", t
    assert t["result_json"]["model_id"] == "kronos_base"
    assert len(t["result_json"]["forecast"]) > 0
    assert t["result_json"]["meta"]["stub"] is True
