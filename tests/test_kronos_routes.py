from __future__ import annotations

import pytest

HEADERS = {"X-API-Key": "test-key"}


@pytest.mark.asyncio
async def test_list_models_ok(client):
    r = await client.get("/v1/models", headers=HEADERS)
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()}
    assert "kronos_base" in ids


@pytest.mark.asyncio
async def test_list_models_filters_by_interval(client):
    r = await client.get("/v1/models?interval=1d", headers=HEADERS)
    assert r.status_code == 200
    for m in r.json():
        assert "1d" in m["supported_intervals"]


@pytest.mark.asyncio
async def test_list_models_rejects_bad_interval(client):
    r = await client.get("/v1/models?interval=17m", headers=HEADERS)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_timeframes_without_ticker(client):
    r = await client.get("/v1/timeframes", headers=HEADERS)
    assert r.status_code == 200
    tfs = r.json()
    assert "1d" in tfs or "5m" in tfs


@pytest.mark.asyncio
async def test_timeframes_unknown_model(client):
    r = await client.get("/v1/timeframes?model_id=kronos_vapor", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_eligibility_ineligible_unsupported_interval(client):
    # 1m is a canonical platform interval but not in any Kronos model's
    # supported_intervals list.
    r = await client.get(
        "/v1/eligibility?model_id=kronos_base&ticker=AAPL&interval=1m",
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "ineligible"
    assert body["reason"] == "UNSUPPORTED_INTERVAL"


@pytest.mark.asyncio
async def test_eligibility_insufficient_history_on_empty_cache(client):
    r = await client.get(
        "/v1/eligibility?model_id=kronos_base&ticker=AAPL&interval=1d",
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "ineligible"
    assert body["reason"] == "INSUFFICIENT_HISTORY"


@pytest.mark.asyncio
async def test_routes_require_api_key(client):
    r = await client.get("/v1/models")
    assert r.status_code in (401, 403)
