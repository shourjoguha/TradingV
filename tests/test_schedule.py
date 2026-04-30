"""Schedule config + runner tick logic."""
from __future__ import annotations

import datetime

import pytest

from app.schedule import runner, service as schedule_svc
from app.schedule.models import ScheduleConfig

HEADERS = {"X-API-Key": "test-key"}


# ----------------------------------------------------------------------
# Pure helpers
# ----------------------------------------------------------------------

def _cfg(**overrides) -> ScheduleConfig:
    base = dict(
        id=1,
        enabled=True,
        tz_name="UTC",
        run_at_local=datetime.time(23, 30),
        intervals=["1d"],
        horizon_bars=5,
        model_ids=["kronos_base"],
        retry_minutes=5,
        collect_actuals=True,
        skip_weekends=True,
        pending_run=False,
    )
    base.update(overrides)
    return ScheduleConfig(**base)


def test_compute_next_run_at_today_in_future():
    # It's Mon 12:00 UTC; run_at_local 23:30 → today at 23:30 UTC.
    now = datetime.datetime(2026, 4, 27, 12, 0, tzinfo=datetime.timezone.utc)
    cfg = _cfg(run_at_local=datetime.time(23, 30))
    nxt = schedule_svc.compute_next_run_at(cfg, now=now)
    assert nxt == datetime.datetime(2026, 4, 27, 23, 30, tzinfo=datetime.timezone.utc)


def test_compute_next_run_at_today_already_past_advances():
    # Mon 23:45 UTC, run_at_local 23:30 → tomorrow (Tue) 23:30.
    now = datetime.datetime(2026, 4, 27, 23, 45, tzinfo=datetime.timezone.utc)
    cfg = _cfg(run_at_local=datetime.time(23, 30))
    nxt = schedule_svc.compute_next_run_at(cfg, now=now)
    assert nxt == datetime.datetime(2026, 4, 28, 23, 30, tzinfo=datetime.timezone.utc)


def test_compute_next_run_at_skips_weekend_to_monday():
    # Fri 23:45 UTC → Sat candidate → push to Mon.
    now = datetime.datetime(2026, 5, 1, 23, 45, tzinfo=datetime.timezone.utc)  # Fri
    cfg = _cfg(run_at_local=datetime.time(23, 30), skip_weekends=True)
    nxt = schedule_svc.compute_next_run_at(cfg, now=now)
    # Sat 5/2 → push past weekend → Mon 5/4.
    assert nxt.weekday() == 0  # Monday
    assert nxt.date() == datetime.date(2026, 5, 4)


def test_compute_next_run_at_no_skip_weekend():
    now = datetime.datetime(2026, 5, 1, 23, 45, tzinfo=datetime.timezone.utc)  # Fri
    cfg = _cfg(skip_weekends=False)
    nxt = schedule_svc.compute_next_run_at(cfg, now=now)
    assert nxt.weekday() == 5  # Saturday


def test_compute_next_run_at_handles_local_tz():
    # New York. 17:00 EDT (Mon) = 21:00 UTC. run_at_local 23:30 NY = 03:30 UTC next day.
    now = datetime.datetime(2026, 6, 1, 21, 0, tzinfo=datetime.timezone.utc)
    cfg = _cfg(tz_name="America/New_York", run_at_local=datetime.time(23, 30))
    nxt = schedule_svc.compute_next_run_at(cfg, now=now)
    # 23:30 EDT is 03:30 UTC the next day.
    assert nxt == datetime.datetime(2026, 6, 2, 3, 30, tzinfo=datetime.timezone.utc)


def test_resolve_tz_falls_back_to_utc():
    tz = schedule_svc.resolve_tz("Not/A/RealZone")
    assert tz is datetime.timezone.utc


def test_is_due_respects_enabled():
    past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    cfg = _cfg(enabled=False, next_run_at=past)
    assert schedule_svc.is_due(cfg) is False


def test_is_due_when_pending():
    far_future = datetime.datetime(2099, 1, 1, tzinfo=datetime.timezone.utc)
    cfg = _cfg(enabled=True, pending_run=True, next_run_at=far_future)
    assert schedule_svc.is_due(cfg) is True


def test_is_due_time_predicate():
    past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    cfg = _cfg(enabled=True, next_run_at=past)
    assert schedule_svc.is_due(cfg) is True


# ----------------------------------------------------------------------
# Service CRUD
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ensure_config_creates_singleton(client):
    cfg = await schedule_svc.ensure_config()
    assert cfg.id == 1
    assert cfg.run_at_local == datetime.time(23, 30)
    assert cfg.model_ids == ["kronos_base"]
    assert cfg.intervals == ["1d"]
    assert cfg.enabled is False  # default opt-in


@pytest.mark.asyncio
async def test_ensure_config_idempotent(client):
    a = await schedule_svc.ensure_config()
    b = await schedule_svc.ensure_config()
    assert a.id == b.id == 1


@pytest.mark.asyncio
async def test_record_run_uses_post_put_config(client):
    """Regression: PUT during _tick must not lose today's slot.

    Sequence:
    - cfg starts at run_at_local=21:30; first scheduled slot fires.
    - Mid-tick (still 21:34 UTC), an operator PUTs run_at_local=23:30.
    - The runner finishes its tick and calls record_run(advance_now=21:35).
    - Expectation: next_run_at should reflect the NEW 23:30 today, not
      yesterday's stale advance computed from the pre-PUT config.
    """
    # Seed a config to a known time so compute_next_run_at is deterministic.
    await schedule_svc.update_config(
        enabled=True,
        tz_name="UTC",
        run_at_local=datetime.time(21, 30),
        intervals=["1d"],
        model_ids=["kronos_base"],
        skip_weekends=False,  # always weekday-eligible
    )

    # Operator PUTs new run_at_local mid-tick.
    await schedule_svc.update_config(run_at_local=datetime.time(23, 30))

    # Runner's _tick finishes and calls record_run with advance_now just
    # after the original slot. record_run must read the post-PUT row and
    # recompute against 23:30, landing today.
    advance_now = datetime.datetime(2026, 4, 30, 21, 35, tzinfo=datetime.timezone.utc)
    await schedule_svc.record_run(status="succeeded", advance_now=advance_now)

    cfg = await schedule_svc.get_config()
    # SQLite drops tzinfo on round-trip; compare naive components.
    actual_naive = cfg.next_run_at.replace(tzinfo=None)
    expected_naive = datetime.datetime(2026, 4, 30, 23, 30)
    assert actual_naive == expected_naive, (
        f"next_run_at should land on today's 23:30 UTC, got {cfg.next_run_at}"
    )
    assert cfg.last_run_status == "succeeded"


@pytest.mark.asyncio
async def test_record_run_without_advance_leaves_next_run_at(client):
    """When advance_now is None, record_run touches last_run_* but not next_run_at."""
    await schedule_svc.update_config(
        enabled=True, run_at_local=datetime.time(21, 30), skip_weekends=False,
    )
    cfg_before = await schedule_svc.get_config()
    await schedule_svc.record_run(status="failed", error="boom")
    cfg_after = await schedule_svc.get_config()

    assert cfg_after.next_run_at == cfg_before.next_run_at
    assert cfg_after.last_run_status == "failed"
    assert cfg_after.last_run_error == "boom"


@pytest.mark.asyncio
async def test_update_config_recomputes_next_run_at(client):
    cfg = await schedule_svc.update_config(enabled=True)
    assert cfg.enabled is True
    assert cfg.next_run_at is not None  # recomputed by update_config


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_schedule_returns_defaults(client):
    r = await client.get("/v1/schedule", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["run_at_local"] == "23:30:00"
    assert body["model_ids"] == ["kronos_base"]


@pytest.mark.asyncio
async def test_put_schedule_partial_update(client):
    r = await client.put(
        "/v1/schedule",
        headers=HEADERS,
        json={"enabled": True, "horizon_bars": 7, "model_ids": ["kronos_base", "kronos_small"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["horizon_bars"] == 7
    assert body["model_ids"] == ["kronos_base", "kronos_small"]
    # Unset fields preserved at defaults.
    assert body["run_at_local"] == "23:30:00"


@pytest.mark.asyncio
async def test_put_schedule_rejects_bad_tz(client):
    r = await client.put(
        "/v1/schedule", headers=HEADERS, json={"tz_name": "Not/A/RealZone"}
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_put_schedule_accepts_iana_tz(client):
    r = await client.put(
        "/v1/schedule", headers=HEADERS, json={"tz_name": "America/New_York"}
    )
    assert r.status_code == 200
    assert r.json()["tz_name"] == "America/New_York"


@pytest.mark.asyncio
async def test_fire_now_sets_pending(client):
    r = await client.post("/v1/schedule/fire-now", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["pending_run"] is True


# ----------------------------------------------------------------------
# Runner tick
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tick_skipped_disabled(client, monkeypatch):
    """Disabled config → no submit_run, no status persisted."""
    submit_calls = []

    async def fake_submit(**kwargs):
        submit_calls.append(kwargs)

    from app.analysis import service as analysis_svc

    monkeypatch.setattr(analysis_svc, "submit_run", fake_submit)

    # ensure config exists, disabled
    await schedule_svc.ensure_config()
    await runner._tick()
    assert submit_calls == []


@pytest.mark.asyncio
async def test_tick_skipped_empty_watchlist(client, monkeypatch):
    submit_calls = []

    async def fake_submit(**kwargs):
        submit_calls.append(kwargs)

    from app.analysis import service as analysis_svc

    monkeypatch.setattr(analysis_svc, "submit_run", fake_submit)

    await schedule_svc.update_config(enabled=True)
    # Force "weekday" by overriding compute path: set tz so today is Mon.
    # Tick will see watchlist empty regardless of weekday.
    await runner._tick()
    cfg = await schedule_svc.get_config()
    assert cfg.last_run_status in ("skipped_empty", "skipped_weekend")
    assert submit_calls == []


@pytest.mark.asyncio
async def test_tick_enqueues_via_queue(client, monkeypatch):
    """Tier-1 queue: scheduler enqueues, worker drains. Tick succeeds as
    soon as the row is enqueued (doesn't wait for actual execution)."""
    enqueue_calls = []

    async def fake_enqueue(*, inputs, source="manual"):
        enqueue_calls.append({"inputs": inputs, "source": source})
        return {"id": "fake-q-1", "status": "pending"}

    from app.queue import service as queue_svc

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)

    # Add a watchlist symbol.
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    # Configure: enabled, no weekend skip (so any day works).
    await schedule_svc.update_config(enabled=True, skip_weekends=False)

    await runner._tick()
    cfg = await schedule_svc.get_config()
    assert cfg.last_run_status == "succeeded", cfg.last_run_error
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0]["source"] == "schedule"
    assert enqueue_calls[0]["inputs"]["tickers"] == ["AAPL"]
    assert enqueue_calls[0]["inputs"]["intervals"] == ["1d"]
    assert enqueue_calls[0]["inputs"]["model_ids"] == ["kronos_base"]
    assert enqueue_calls[0]["inputs"]["horizon_bars"] == 5


# (test_tick_handles_at_capacity removed: under Tier-1 queue, scheduler
# enqueues unconditionally and the AtCapacityError path is unreachable
# from the schedule runner. Concurrency-gate semantics still tested in
# tests/test_concurrency.py via direct service.submit_run calls.)


@pytest.mark.asyncio
async def test_tick_collects_actuals_after_run(client, monkeypatch):
    async def fake_enqueue(*, inputs, source="manual"):
        return {"id": "fake-q-actuals", "status": "pending"}

    refresh_calls = []

    async def fake_refresh(sym, interval, **_):
        refresh_calls.append((sym, interval))
        return 100

    from app.queue import service as queue_svc
    from app.market_data import service as md_service

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)
    monkeypatch.setattr(md_service, "refresh", fake_refresh)

    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "MSFT"})
    await schedule_svc.update_config(
        enabled=True, skip_weekends=False, intervals=["1d"], collect_actuals=True
    )

    await runner._tick()
    cfg = await schedule_svc.get_config()
    assert cfg.last_run_status == "succeeded"
    assert set(refresh_calls) == {("AAPL", "1d"), ("MSFT", "1d")}


@pytest.mark.asyncio
async def test_tick_skips_actuals_when_collect_disabled(client, monkeypatch):
    class FakeJob:
        id = "fake-job"
        task_count = 1

    async def fake_submit(**kwargs):
        return FakeJob()

    refresh_calls = []

    async def fake_refresh(*args, **kwargs):
        refresh_calls.append((args, kwargs))
        return 0

    from app.queue import service as queue_svc
    from app.market_data import service as md_service

    async def fake_enqueue(*, inputs, source="manual"):
        return {"id": "fake-q", "status": "pending"}

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)
    monkeypatch.setattr(md_service, "refresh", fake_refresh)

    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await schedule_svc.update_config(
        enabled=True, skip_weekends=False, collect_actuals=False
    )

    await runner._tick()
    assert refresh_calls == []


@pytest.mark.asyncio
async def test_actuals_failure_does_not_fail_scheduled_run(client, monkeypatch):
    async def fake_enqueue(*, inputs, source="manual"):
        return {"id": "fake-q", "status": "pending"}

    async def boom_refresh(*args, **kwargs):
        raise RuntimeError("provider down")

    from app.queue import service as queue_svc
    from app.market_data import service as md_service

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)
    monkeypatch.setattr(md_service, "refresh", boom_refresh)

    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await schedule_svc.update_config(
        enabled=True, skip_weekends=False, collect_actuals=True
    )

    await runner._tick()
    cfg = await schedule_svc.get_config()
    # Run still recorded as succeeded — actuals failure is best-effort.
    assert cfg.last_run_status == "succeeded"


@pytest.mark.asyncio
async def test_tick_runs_crypto_on_weekend_when_skip_weekends_true(
    client, monkeypatch
):
    """Per-asset-class filter: stocks skipped on Sat, crypto runs."""
    enqueue_calls = []

    async def fake_enqueue(*, inputs, source="manual"):
        enqueue_calls.append(inputs)
        return {"id": "fake-q", "status": "pending"}

    from app.queue import service as queue_svc

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)

    # Force the local clock to a Saturday.
    saturday = datetime.datetime(2026, 4, 25, 14, 0, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(runner, "_now_utc", lambda: saturday)

    # Add an equity (stock) and a crypto. Mock asset_class on the registry.
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "BTC-USD"})
    await client.patch(
        "/v1/tickers/AAPL", headers=HEADERS, json={"asset_class": "stock"}
    )
    await client.patch(
        "/v1/tickers/BTC-USD", headers=HEADERS, json={"asset_class": "crypto"}
    )
    await schedule_svc.update_config(enabled=True, skip_weekends=True)

    await runner._tick()
    cfg = await schedule_svc.get_config()
    assert cfg.last_run_status == "succeeded"
    assert len(enqueue_calls) == 1
    # Only crypto fired — AAPL skipped because Saturday.
    assert enqueue_calls[0]["tickers"] == ["BTC-USD"]


@pytest.mark.asyncio
async def test_tick_skipped_weekend_when_only_stocks_present(
    client, monkeypatch
):
    enqueue_calls = []

    async def fake_enqueue(*, inputs, source="manual"):
        enqueue_calls.append(inputs)
        return {"id": "fake-q", "status": "pending"}

    from app.queue import service as queue_svc

    monkeypatch.setattr(queue_svc, "enqueue", fake_enqueue)

    saturday = datetime.datetime(2026, 4, 25, 14, 0, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(runner, "_now_utc", lambda: saturday)

    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await client.patch(
        "/v1/tickers/AAPL", headers=HEADERS, json={"asset_class": "stock"}
    )
    await schedule_svc.update_config(enabled=True, skip_weekends=True)

    await runner._tick()
    cfg = await schedule_svc.get_config()
    assert cfg.last_run_status == "skipped_weekend"
    assert enqueue_calls == []


@pytest.mark.asyncio
async def test_request_wake_safe_when_runner_not_started():
    runner._wake_event = None
    runner.request_wake()  # must not raise


@pytest.mark.asyncio
async def test_request_wake_sets_event():
    import asyncio

    runner._wake_event = asyncio.Event()
    runner.request_wake()
    assert runner._wake_event.is_set()
