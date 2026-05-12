"""/v1/admin/loops endpoints — list, fire, abort, cadence."""
from __future__ import annotations

import asyncio

import pytest

from app.admin import lifespan as _admin_lifespan
from app.admin import loops as _loops_meta
from app.admin import runtime as _runtime
from app.admin import service as _svc

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def reset_runtime():
    _runtime.clear()
    yield
    _runtime.clear()


@pytest.mark.asyncio
async def test_list_loops_returns_all_registered_meta(client):
    r = await client.get("/v1/admin/loops", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == len(_loops_meta.LOOPS)
    ids = {row["loop_id"] for row in data["items"]}
    assert "macro" in ids
    assert "research_weekly" in ids
    assert "queue_worker" in ids


@pytest.mark.asyncio
async def test_fire_unknown_loop_404(client):
    r = await client.post("/v1/admin/loops/no_such/fire", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_fire_no_handle_400(client):
    # Loop is in registry but no handle registered → manual fire not supported.
    r = await client.post("/v1/admin/loops/macro/fire", headers=HEADERS)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_fire_calls_callable(client):
    fired = asyncio.Event()

    async def _fire():
        fired.set()

    _admin_lifespan.register_handle("macro", fire_now=_fire)
    r = await client.post("/v1/admin/loops/macro/fire", headers=HEADERS)
    assert r.status_code == 200
    # Background task should run.
    await asyncio.wait_for(fired.wait(), timeout=2.0)


@pytest.mark.asyncio
async def test_fire_debounce_returns_429(client):
    fired_count = 0

    async def _fire():
        nonlocal fired_count
        fired_count += 1

    _admin_lifespan.register_handle("macro", fire_now=_fire)
    r1 = await client.post("/v1/admin/loops/macro/fire", headers=HEADERS)
    r2 = await client.post("/v1/admin/loops/macro/fire", headers=HEADERS)
    r3 = await client.post("/v1/admin/loops/macro/fire", headers=HEADERS)
    assert r1.status_code == 200
    assert r2.status_code == 429
    assert r3.status_code == 429
    body = r2.json()
    assert "retry_after_seconds" in body["detail"]


@pytest.mark.asyncio
async def test_abort_supported_loop(client):
    stop_evt = asyncio.Event()
    _admin_lifespan.register_handle("macro", stop_event=stop_evt)
    r = await client.post("/v1/admin/loops/macro/abort", headers=HEADERS)
    assert r.status_code == 200
    assert stop_evt.is_set()


@pytest.mark.asyncio
async def test_update_cadence(client):
    r = await client.put(
        "/v1/admin/loops/macro/cadence",
        headers=HEADERS,
        json={"cadence_seconds": 7200, "enabled": False},
    )
    assert r.status_code == 200
    # Round-trip through DB.
    cad = await _svc.get_setting("loop.cadence.macro")
    en = await _svc.get_setting("loop.enabled.macro")
    assert cad == 7200
    assert en is False


@pytest.mark.asyncio
async def test_record_tick_writes_status(client):
    async with _admin_lifespan.tick_status("macro"):
        await asyncio.sleep(0)  # nothing fancy; success path
    s = await _svc.get_status("macro")
    assert s is not None
    assert s.last_tick_ok is True
    assert s.last_duration_ms is not None
    assert s.last_error is None


@pytest.mark.asyncio
async def test_record_tick_records_failure(client):
    err = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        async with _admin_lifespan.tick_status("opps"):
            raise err
    s = await _svc.get_status("opps")
    assert s is not None
    assert s.last_tick_ok is False
    assert "boom" in (s.last_error or "")


@pytest.mark.asyncio
async def test_settings_endpoint_lists_known_keys(client):
    r = await client.get("/v1/admin/settings", headers=HEADERS)
    assert r.status_code == 200
    items = r.json()["items"]
    assert "anthropic.enabled" in items
    assert "anthropic.monthly_cap_usd" in items
    assert "anthropic.kill_switch_active" in items


@pytest.mark.asyncio
async def test_set_setting_endpoint_whitelist(client):
    r = await client.put(
        "/v1/admin/settings/anthropic.enabled",
        headers=HEADERS,
        json={"value": False},
    )
    assert r.status_code == 200
    val = await _svc.get_setting("anthropic.enabled")
    assert val is False


@pytest.mark.asyncio
async def test_set_setting_endpoint_rejects_random_key(client):
    r = await client.put(
        "/v1/admin/settings/random.key",
        headers=HEADERS,
        json={"value": True},
    )
    assert r.status_code == 400
