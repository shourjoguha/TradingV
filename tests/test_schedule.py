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
async def test_tick_invokes_submit_run(client, monkeypatch):
    submit_calls = []

    class FakeJob:
        id = "fake-job"
        task_count = 1

    async def fake_submit(**kwargs):
        submit_calls.append(kwargs)
        return FakeJob()

    from app.analysis import service as analysis_svc

    monkeypatch.setattr(analysis_svc, "submit_run", fake_submit)

    # Add a watchlist symbol.
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    # Configure: enabled, no weekend skip (so any day works).
    await schedule_svc.update_config(enabled=True, skip_weekends=False)

    await runner._tick()
    cfg = await schedule_svc.get_config()
    assert cfg.last_run_status == "succeeded", cfg.last_run_error
    assert len(submit_calls) == 1
    assert submit_calls[0]["tickers"] == ["AAPL"]
    assert submit_calls[0]["intervals"] == ["1d"]
    assert submit_calls[0]["model_ids"] == ["kronos_base"]
    assert submit_calls[0]["horizon_bars"] == 5


@pytest.mark.asyncio
async def test_tick_handles_at_capacity(client, monkeypatch):
    from app.analysis import concurrency, service as analysis_svc

    async def fake_submit(**kwargs):
        raise concurrency.AtCapacityError("busy")

    monkeypatch.setattr(analysis_svc, "submit_run", fake_submit)

    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await schedule_svc.update_config(enabled=True, skip_weekends=False)

    await runner._tick()
    cfg = await schedule_svc.get_config()
    assert cfg.last_run_status == "deferred_429"
    assert cfg.pending_run is True


@pytest.mark.asyncio
async def test_tick_collects_actuals_after_run(client, monkeypatch):
    class FakeJob:
        id = "fake-job"
        task_count = 1

    async def fake_submit(**kwargs):
        return FakeJob()

    refresh_calls = []

    async def fake_refresh(sym, interval, **_):
        refresh_calls.append((sym, interval))
        return 100

    from app.analysis import service as analysis_svc
    from app.market_data import service as md_service

    monkeypatch.setattr(analysis_svc, "submit_run", fake_submit)
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

    from app.analysis import service as analysis_svc
    from app.market_data import service as md_service

    monkeypatch.setattr(analysis_svc, "submit_run", fake_submit)
    monkeypatch.setattr(md_service, "refresh", fake_refresh)

    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await schedule_svc.update_config(
        enabled=True, skip_weekends=False, collect_actuals=False
    )

    await runner._tick()
    assert refresh_calls == []


@pytest.mark.asyncio
async def test_actuals_failure_does_not_fail_scheduled_run(client, monkeypatch):
    class FakeJob:
        id = "fake-job"
        task_count = 1

    async def fake_submit(**kwargs):
        return FakeJob()

    async def boom_refresh(*args, **kwargs):
        raise RuntimeError("provider down")

    from app.analysis import service as analysis_svc
    from app.market_data import service as md_service

    monkeypatch.setattr(analysis_svc, "submit_run", fake_submit)
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
async def test_request_wake_safe_when_runner_not_started():
    runner._wake_event = None
    runner.request_wake()  # must not raise


@pytest.mark.asyncio
async def test_request_wake_sets_event():
    import asyncio

    runner._wake_event = asyncio.Event()
    runner.request_wake()
    assert runner._wake_event.is_set()
