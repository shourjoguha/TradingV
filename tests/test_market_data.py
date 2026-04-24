import datetime
from typing import List

import pytest

from app.market_data import registry
from app.market_data.providers.base import Bar, UnsupportedRequest

HEADERS = {"X-API-Key": "test-key"}


class FakeProvider:
    """Deterministic provider for tests. No network."""

    name = "fake"

    def __init__(self, bars: List[Bar], supports_assets=("stock", "etf", "crypto")):
        self._bars = bars
        self._assets = supports_assets
        self.calls = 0

    def supports(self, asset_class: str, interval: str) -> bool:
        return asset_class in self._assets and interval in {"1d", "1h", "5m"}

    async def fetch_ohlcv(self, symbol, asset_class, interval, start=None, end=None):
        self.calls += 1
        if not self.supports(asset_class, interval):
            raise UnsupportedRequest(asset_class=asset_class, interval=interval)
        return list(self._bars)


@pytest.fixture(autouse=True)
def _reset_providers():
    registry.reset_to_defaults()
    yield
    registry.reset_to_defaults()


def _sample_bars(n: int = 5, start_ts: datetime.datetime | None = None) -> List[Bar]:
    start_ts = start_ts or datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    out = []
    for i in range(n):
        ts = start_ts + datetime.timedelta(days=i)
        out.append(
            Bar(
                ts=ts,
                open=100 + i,
                high=101 + i,
                low=99 + i,
                close=100.5 + i,
                volume=1_000_000 + i,
                amount=None,
            )
        )
    return out


@pytest.mark.asyncio
async def test_list_intervals(client):
    r = await client.get("/v1/intervals", headers=HEADERS)
    assert r.status_code == 200
    assert "1d" in r.json()
    assert "1h" in r.json()


@pytest.mark.asyncio
async def test_ohlcv_unsupported_interval(client):
    r = await client.get(
        "/v1/ohlcv", params={"symbol": "AAPL", "interval": "3d"}, headers=HEADERS
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_ohlcv_refresh_and_read(client):
    fake = FakeProvider(_sample_bars(10))
    registry._PROVIDERS.clear()
    registry.register(fake, prepend=True)

    # Seed a ticker first so asset class is known.
    await client.post("/v1/tickers", json={"symbol": "AAPL"}, headers=HEADERS)

    r = await client.get(
        "/v1/ohlcv",
        params={"symbol": "aapl", "interval": "1d", "refresh": True, "limit": 5},
        headers=HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "AAPL"
    assert data["count"] == 5  # limited
    assert fake.calls == 1

    # Bars ordered ascending ts.
    ts_list = [b["ts"] for b in data["bars"]]
    assert ts_list == sorted(ts_list)

    # Second read without refresh → cache only, provider not re-called.
    r2 = await client.get(
        "/v1/ohlcv",
        params={"symbol": "AAPL", "interval": "1d"},
        headers=HEADERS,
    )
    assert r2.status_code == 200
    # No `limit` passed → default 500, returns all 10 cached bars.
    assert r2.json()["count"] == 10
    assert fake.calls == 1  # unchanged


@pytest.mark.asyncio
async def test_ohlcv_refresh_upserts_dedup(client):
    # Same ts twice → row count stays, values update (no duplicates).
    bars_v1 = _sample_bars(3)
    bars_v2 = [
        Bar(ts=b.ts, open=b.open + 50, high=b.high + 50, low=b.low + 50,
            close=b.close + 50, volume=b.volume, amount=None)
        for b in bars_v1
    ]
    fake = FakeProvider(bars_v1)
    registry._PROVIDERS.clear()
    registry.register(fake, prepend=True)

    await client.post("/v1/tickers", json={"symbol": "MSFT"}, headers=HEADERS)
    await client.get(
        "/v1/ohlcv",
        params={"symbol": "MSFT", "interval": "1d", "refresh": True},
        headers=HEADERS,
    )

    # Second refresh with different values for the same ts.
    fake._bars = bars_v2
    r = await client.get(
        "/v1/ohlcv",
        params={"symbol": "MSFT", "interval": "1d", "refresh": True},
        headers=HEADERS,
    )
    data = r.json()
    assert data["count"] == 3  # dedup worked
    # New open values applied.
    assert all(b["open"] >= 150 for b in data["bars"])


@pytest.mark.asyncio
async def test_ohlcv_auto_registers_ticker(client):
    fake = FakeProvider(_sample_bars(2))
    registry._PROVIDERS.clear()
    registry.register(fake, prepend=True)

    # Symbol not in registry yet.
    r = await client.get(
        "/v1/ohlcv",
        params={"symbol": "newco", "interval": "1d", "refresh": True},
        headers=HEADERS,
    )
    assert r.status_code == 200

    # Auto-registered with source=analysis.
    r = await client.get("/v1/tickers/NEWCO", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["source"] == "analysis"


@pytest.mark.asyncio
async def test_ohlcv_provider_rejects(client):
    fake = FakeProvider(_sample_bars(1), supports_assets=("stock",))
    registry._PROVIDERS.clear()
    registry.register(fake, prepend=True)

    # Crypto not supported by fake.
    await client.post("/v1/tickers", json={"symbol": "BTC-USD"}, headers=HEADERS)
    r = await client.get(
        "/v1/ohlcv",
        params={"symbol": "BTC-USD", "interval": "1d", "refresh": True},
        headers=HEADERS,
    )
    assert r.status_code == 422
