"""Phase 2 — Alpha Vantage provider + /v1/api-list catalog."""
from __future__ import annotations

import datetime

import pytest

from app.core.config import SETTINGS
from app.market_data.providers.alphavantage_provider import (
    AlphaVantageProvider,
    _parse_series,
)
from app.market_data.providers.base import UnsupportedRequest

HEADERS = {"X-API-Key": "test-key"}


# --- provider unit tests (no network) --------------------------------------

def test_provider_self_disables_without_key():
    p = AlphaVantageProvider(api_key="")
    assert p.configured is False
    assert p.supports("stock", "1d") is False  # unkeyed => skipped by registry


def test_provider_support_matrix_when_keyed():
    p = AlphaVantageProvider(api_key="DEMO")
    assert p.configured is True
    assert p.supports("stock", "1d") is True
    assert p.supports("etf", "5m") is True
    assert p.supports("stock", "1w") is True
    assert p.supports("crypto", "1d") is False  # stocks/ETFs only
    assert p.supports("stock", "3m") is False  # not a canonical interval we map


@pytest.mark.asyncio
async def test_provider_fetch_unsupported_raises():
    p = AlphaVantageProvider(api_key="DEMO")
    with pytest.raises(UnsupportedRequest):
        await p.fetch_ohlcv("AAPL", "crypto", "1d")


def test_parse_series_daily():
    series = {
        "2026-06-26": {
            "1. open": "100.0",
            "2. high": "110.0",
            "3. low": "99.0",
            "4. close": "105.0",
            "5. volume": "1000",
        },
        "2026-06-25": {
            "1. open": "90.0",
            "2. high": "95.0",
            "3. low": "89.0",
            "4. close": "94.0",
            "5. volume": "2000",
        },
    }
    bars = _parse_series(series, "1d", None, None)
    assert len(bars) == 2
    # ascending ts order
    assert bars[0].ts < bars[1].ts
    assert bars[1].close == 105.0
    assert bars[0].ts.tzinfo is not None  # tz-aware UTC


def test_parse_series_respects_window():
    series = {
        "2026-06-26": {"1. open": "1", "2. high": "1", "3. low": "1", "4. close": "1", "5. volume": "1"},
        "2026-01-01": {"1. open": "1", "2. high": "1", "3. low": "1", "4. close": "1", "5. volume": "1"},
    }
    start = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
    bars = _parse_series(series, "1d", start, None)
    assert len(bars) == 1
    assert bars[0].ts.date() == datetime.date(2026, 6, 26)


# --- /v1/api-list endpoint --------------------------------------------------

@pytest.mark.asyncio
async def test_api_list_lists_yfinance(client):
    r = await client.get("/v1/api-list", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    names = {p["name"] for p in body["ohlcv_providers"]}
    assert "yfinance" in names
    yf = next(p for p in body["ohlcv_providers"] if p["name"] == "yfinance")
    assert yf["category"] == "ohlcv"
    assert yf["enabled"] is True
    assert yf["configured"] is True  # keyless provider
    assert "1d" in yf["intervals"]
    assert "stock" in yf["asset_classes"]


@pytest.mark.asyncio
async def test_api_list_reports_agent_feed_configured_status(client):
    prev = SETTINGS.ALPHAVANTAGE_API_KEY
    SETTINGS.ALPHAVANTAGE_API_KEY = "DEMO"
    try:
        r = await client.get("/v1/api-list", headers=HEADERS)
        assert r.status_code == 200
        feeds = {f["name"]: f for f in r.json()["agent_feeds"]}
        assert feeds["alpha_vantage_fundamentals"]["configured"] is True
        assert feeds["finnhub"]["configured"] is False  # no key set
        assert feeds["stocktwits"]["configured"] is True  # keyless public feed
    finally:
        SETTINGS.ALPHAVANTAGE_API_KEY = prev


@pytest.mark.asyncio
async def test_api_list_requires_auth(client):
    r = await client.get("/v1/api-list")
    assert r.status_code in (401, 403)
