import pytest

HEADERS = {"X-API-Key": "test-key"}


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_webhook_requires_api_key(client):
    r = await client.post(
        "/webhook",
        json={"ticker": "AAPL", "alert_type": "x", "payload_json": {}},
    )
    # Missing key rejected by APIKeyHeader.
    assert r.status_code in (401, 403)
    # Wrong key rejected by verify_api_key → 403.
    r2 = await client.post(
        "/webhook",
        json={"ticker": "AAPL", "alert_type": "x", "payload_json": {}},
        headers={"X-API-Key": "wrong"},
    )
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_webhook_then_alerts_flow(client):
    payload = {"ticker": "AAPL", "alert_type": "breakout", "payload_json": {"price": 100}}
    r = await client.post("/webhook", json=payload, headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

    r = await client.get("/alerts", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "AAPL"
    assert data[0]["is_read"] is True

    # Second read returns empty (destructive read preserved).
    r = await client.get("/alerts", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_alerts_bad_key(client):
    r = await client.get("/alerts", headers={"X-API-Key": "nope"})
    assert r.status_code == 403
