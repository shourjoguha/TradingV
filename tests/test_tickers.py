import pytest

HEADERS = {"X-API-Key": "test-key"}


@pytest.mark.asyncio
async def test_list_empty(client):
    r = await client.get("/v1/tickers", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_manual_single_create(client):
    r = await client.post(
        "/v1/tickers",
        json={"symbol": "aapl"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["asset_class"] == "stock"
    assert data[0]["source"] == "manual"


@pytest.mark.asyncio
async def test_manual_bulk_create(client):
    r = await client.post(
        "/v1/tickers",
        json={"tickers": [{"symbol": "btc-usd"}, {"symbol": "SPY"}, {"symbol": "msft"}]},
        headers=HEADERS,
    )
    assert r.status_code == 200
    by_sym = {t["symbol"]: t for t in r.json()}
    assert by_sym["BTC-USD"]["asset_class"] == "crypto"
    assert by_sym["SPY"]["asset_class"] == "etf"
    assert by_sym["MSFT"]["asset_class"] == "stock"


@pytest.mark.asyncio
async def test_idempotent_upsert(client):
    await client.post("/v1/tickers", json={"symbol": "NVDA"}, headers=HEADERS)
    await client.post("/v1/tickers", json={"symbol": "nvda"}, headers=HEADERS)
    r = await client.get("/v1/tickers", headers=HEADERS)
    syms = [t["symbol"] for t in r.json()]
    assert syms.count("NVDA") == 1


@pytest.mark.asyncio
async def test_patch_asset_class_override(client):
    await client.post("/v1/tickers", json={"symbol": "SOXL"}, headers=HEADERS)
    # SOXL is in known ETF list — override to stock to confirm patch works.
    r = await client.patch(
        "/v1/tickers/SOXL",
        json={"asset_class": "stock", "notes": "3x leveraged"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["asset_class"] == "stock"
    assert r.json()["notes"] == "3x leveraged"


@pytest.mark.asyncio
async def test_patch_missing(client):
    r = await client.patch(
        "/v1/tickers/NOPE", json={"asset_class": "stock"}, headers=HEADERS
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_webhook_populates_tickers(client):
    r = await client.post(
        "/webhook",
        json={"ticker": "googl", "alert_type": "breakout", "payload_json": {}},
        headers=HEADERS,
    )
    assert r.status_code == 200

    r = await client.get("/v1/tickers", headers=HEADERS)
    data = r.json()
    assert any(t["symbol"] == "GOOGL" and t["source"] == "alert" for t in data)


@pytest.mark.asyncio
async def test_search(client):
    await client.post(
        "/v1/tickers",
        json={"tickers": [{"symbol": "AAPL"}, {"symbol": "AMZN"}, {"symbol": "TSLA"}]},
        headers=HEADERS,
    )
    r = await client.get("/v1/tickers/search", params={"q": "A"}, headers=HEADERS)
    syms = [t["symbol"] for t in r.json()]
    assert "AAPL" in syms
    assert "AMZN" in syms
    assert "TSLA" in syms  # contains 'A'


@pytest.mark.asyncio
async def test_filter_by_asset_class(client):
    await client.post(
        "/v1/tickers",
        json={"tickers": [{"symbol": "BTC-USD"}, {"symbol": "AAPL"}, {"symbol": "QQQ"}]},
        headers=HEADERS,
    )
    r = await client.get(
        "/v1/tickers", params={"asset_class": "crypto"}, headers=HEADERS
    )
    syms = [t["symbol"] for t in r.json()]
    assert syms == ["BTC-USD"]
