"""Phase B4 — Railway-fallback inference.

Tests the per-tick gating logic. Doesn't run the actual asyncio loop —
just calls ``_fallback_tick`` directly with monkeypatched clock + adapter.
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from app.analysis.models import AnalysisJob, AnalysisTask
from app.core import db as _db
from app.predictions.models import PredictionPoint
from app.schedule import runner, service as schedule_svc

HEADERS = {"X-API-Key": "test-key"}


def _today_utc() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


async def _seed_prediction_today(*, ticker: str):
    """Insert a `made_on=today` prediction so dedupe skips this ticker."""
    today = _today_utc()
    async with _db.SessionLocal() as session:
        # The PP table requires a task FK; create a stub job + task.
        job_id = f"job-{ticker}"
        task_id = f"task-{ticker}"
        session.add(
            AnalysisJob(
                id=job_id, status="done", inputs_json={}, task_count=1,
                origin="self",
            )
        )
        session.add(
            AnalysisTask(
                id=task_id, job_id=job_id, ticker=ticker, interval="1d",
                model_id="kronos_base", status="done",
            )
        )
        # Flush so the FK target rows are visible before PredictionPoint insert.
        await session.flush()
        session.add(
            PredictionPoint(
                task_id=task_id, ticker=ticker, model_id="kronos_base",
                interval="1d", made_on=today, made_on_dow=today.weekday(),
                target_date=today + datetime.timedelta(days=1),
                target_ts=datetime.datetime.combine(
                    today + datetime.timedelta(days=1),
                    datetime.time(0, 0, tzinfo=datetime.timezone.utc),
                ),
                horizon_offset=1,
                open=1, high=1, low=1, close=1,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_fallback_skips_when_disabled(client, monkeypatch):
    submit_calls = []

    async def fake_enqueue(*, inputs, source="manual"):
        submit_calls.append(inputs)
        return {"id": "fake-q", "status": "pending"}

    from app.queue import service as queue_svc

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)

    # Config disabled by default.
    await schedule_svc.ensure_config()
    await runner._fallback_tick()
    assert submit_calls == []


@pytest.mark.asyncio
async def test_fallback_skips_before_deadline(client, monkeypatch):
    submit_calls = []

    async def fake_enqueue(*, inputs, source="manual"):
        submit_calls.append(inputs)
        return {"id": "fake-q", "status": "pending"}

    from app.queue import service as queue_svc

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)

    # Deadline = run_at_local + 6 hours. Pick a time that's ALWAYS in the
    # future regardless of clock by setting run_at_local to a near-future
    # local time — easier: set fallback_offset_hours large, run_at_local 23:30,
    # only fire if now is after 05:30 next day. Below we just trust default
    # config and verify "now" is unlikely to be exactly past the deadline
    # for today. To be deterministic, monkeypatch the runner's _now_utc.

    fake_now = datetime.datetime(2026, 4, 27, 12, 0, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(runner, "_now_utc", lambda: fake_now)

    # Default cfg: tz=UTC, run_at_local=23:30, fallback_offset=6h →
    # deadline = 27th 23:30 + 6h = 28th 05:30 UTC. Now is 27th 12:00 → before.
    await schedule_svc.update_config(enabled=True)
    await runner._fallback_tick()
    assert submit_calls == []


@pytest.mark.asyncio
async def test_fallback_fires_after_deadline_with_empty_predictions(
    client, monkeypatch
):
    submit_calls = []

    async def fake_enqueue(*, inputs, source="manual"):
        submit_calls.append(inputs)
        return {"id": "fake-q", "status": "pending"}

    from app.queue import service as queue_svc

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)

    # 28th 06:00 UTC: past 28th 05:30 deadline (= 27th 23:30 + 6h).
    fake_now = datetime.datetime(2026, 4, 28, 6, 0, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(runner, "_now_utc", lambda: fake_now)

    await schedule_svc.update_config(enabled=True)
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "MSFT"})

    await runner._fallback_tick()
    assert len(submit_calls) == 1
    assert set(submit_calls[0]["tickers"]) == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_fallback_dedupes_per_ticker(client, monkeypatch):
    submit_calls = []

    async def fake_enqueue(*, inputs, source="manual"):
        submit_calls.append(inputs)
        return {"id": "fake-q", "status": "pending"}

    from app.queue import service as queue_svc

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)

    fake_now = datetime.datetime.combine(
        _today_utc(), datetime.time(23, 0), tzinfo=datetime.timezone.utc
    ) + datetime.timedelta(hours=8)
    monkeypatch.setattr(runner, "_now_utc", lambda: fake_now)

    await schedule_svc.update_config(enabled=True)
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "MSFT"})

    # Pretend AAPL's forecast already landed (laptop pushed earlier).
    await _seed_prediction_today(ticker="AAPL")

    await runner._fallback_tick()
    # Only MSFT should fire — AAPL is deduped.
    assert len(submit_calls) == 1
    assert submit_calls[0]["tickers"] == ["MSFT"]


@pytest.mark.asyncio
async def test_fallback_skips_when_all_tickers_already_predicted(
    client, monkeypatch
):
    submit_calls = []

    async def fake_enqueue(*, inputs, source="manual"):
        submit_calls.append(inputs)
        return {"id": "fake-q", "status": "pending"}

    from app.queue import service as queue_svc

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)

    fake_now = datetime.datetime.combine(
        _today_utc(), datetime.time(23, 0), tzinfo=datetime.timezone.utc
    ) + datetime.timedelta(hours=8)
    monkeypatch.setattr(runner, "_now_utc", lambda: fake_now)

    await schedule_svc.update_config(enabled=True)
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await _seed_prediction_today(ticker="AAPL")

    await runner._fallback_tick()
    assert submit_calls == []


@pytest.mark.asyncio
async def test_fallback_only_starts_on_railway(client, monkeypatch):
    """`start()` must skip the fallback task when INSTANCE_NAME != 'railway'
    OR RAILWAY_FALLBACK_ENABLED is false."""
    monkeypatch.setattr(runner.SETTINGS, "RAILWAY_FALLBACK_ENABLED", True)
    monkeypatch.setattr(runner.SETTINGS, "INSTANCE_NAME", "laptop")

    runner._fallback_task = None
    runner.start()
    assert runner._fallback_task is None  # not started on laptop
    await runner.stop()


@pytest.mark.asyncio
async def test_fallback_starts_when_explicitly_enabled_on_railway(
    client, monkeypatch
):
    monkeypatch.setattr(runner.SETTINGS, "RAILWAY_FALLBACK_ENABLED", True)
    monkeypatch.setattr(runner.SETTINGS, "INSTANCE_NAME", "railway")

    runner._fallback_task = None
    runner.start()
    assert runner._fallback_task is not None
    assert not runner._fallback_task.done()
    await runner.stop()
