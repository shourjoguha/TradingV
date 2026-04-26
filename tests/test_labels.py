"""Ticker labels CRUD + ?labels= filter on watchlist."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core import db as _db
from app.labels import service as labels_svc
from app.labels.models import TickerLabel
from app.tickers.models import Ticker

HEADERS = {"X-API-Key": "test-key"}


# ----------------------------------------------------------------------
# Pure parser
# ----------------------------------------------------------------------

def test_parse_labels_filter_simple():
    assert labels_svc.parse_labels_filter("sector:tech") == [("sector", "tech")]


def test_parse_labels_filter_csv():
    parsed = labels_svc.parse_labels_filter("sector:tech,capsize:large")
    assert parsed == [("sector", "tech"), ("capsize", "large")]


def test_parse_labels_filter_json_values():
    # bool, int, list parse via JSON.
    assert labels_svc.parse_labels_filter("insider_buy:true") == [("insider_buy", True)]
    assert labels_svc.parse_labels_filter("priority:5") == [("priority", 5)]


def test_parse_labels_filter_string_fallback():
    # Non-JSON values stay as strings.
    assert labels_svc.parse_labels_filter("region:us-non-east") == [
        ("region", "us-non-east")
    ]


def test_parse_labels_filter_empty():
    assert labels_svc.parse_labels_filter(None) == []
    assert labels_svc.parse_labels_filter("") == []
    assert labels_svc.parse_labels_filter("malformed") == []


# ----------------------------------------------------------------------
# CRUD via routes
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_label_creates_ticker_and_label(client):
    r = await client.put(
        "/v1/tickers/aapl/labels/sector",
        headers=HEADERS,
        json={"value": "tech"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["key"] == "sector"
    assert body["value"] == "tech"

    # Ticker auto-upserted into registry.
    async with _db.SessionLocal() as session:
        assert await session.get(Ticker, "AAPL") is not None


@pytest.mark.asyncio
async def test_put_label_idempotent_updates_value(client):
    await client.put(
        "/v1/tickers/AAPL/labels/sector", headers=HEADERS, json={"value": "tech"}
    )
    r = await client.put(
        "/v1/tickers/AAPL/labels/sector", headers=HEADERS, json={"value": "consumer"}
    )
    assert r.status_code == 200
    assert r.json()["value"] == "consumer"

    async with _db.SessionLocal() as session:
        rows = (await session.execute(select(TickerLabel))).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_label_supports_bool_list_dict(client):
    # bool
    await client.put(
        "/v1/tickers/AAPL/labels/insider_buy", headers=HEADERS, json={"value": True}
    )
    r = await client.get("/v1/tickers/AAPL/labels/insider_buy", headers=HEADERS)
    assert r.json()["value"] is True

    # list
    await client.put(
        "/v1/tickers/AAPL/labels/hedge_funds",
        headers=HEADERS,
        json={"value": ["citadel", "renaissance"]},
    )
    r = await client.get("/v1/tickers/AAPL/labels/hedge_funds", headers=HEADERS)
    assert r.json()["value"] == ["citadel", "renaissance"]


@pytest.mark.asyncio
async def test_get_missing_label_404(client):
    await client.put(
        "/v1/tickers/AAPL/labels/sector", headers=HEADERS, json={"value": "tech"}
    )
    r = await client.get("/v1/tickers/AAPL/labels/sector", headers=HEADERS)
    assert r.status_code == 200
    r2 = await client.get("/v1/tickers/AAPL/labels/notset", headers=HEADERS)
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_list_labels(client):
    await client.put(
        "/v1/tickers/AAPL/labels/sector", headers=HEADERS, json={"value": "tech"}
    )
    await client.put(
        "/v1/tickers/AAPL/labels/capsize", headers=HEADERS, json={"value": "large"}
    )
    r = await client.get("/v1/tickers/AAPL/labels", headers=HEADERS)
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert {l["key"] for l in body["labels"]} == {"sector", "capsize"}


@pytest.mark.asyncio
async def test_bulk_upsert(client):
    r = await client.put(
        "/v1/tickers/AAPL/labels",
        headers=HEADERS,
        json={
            "labels": {
                "sector": "tech",
                "capsize": "large",
                "insider_buy": True,
                "hedge_funds": ["citadel"],
                "planned_horizon": "quarters",
            }
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["labels"]) == 5
    keys = {l["key"]: l["value"] for l in body["labels"]}
    assert keys["sector"] == "tech"
    assert keys["insider_buy"] is True
    assert keys["hedge_funds"] == ["citadel"]


@pytest.mark.asyncio
async def test_bulk_upsert_partial_does_not_remove_others(client):
    await client.put(
        "/v1/tickers/AAPL/labels",
        headers=HEADERS,
        json={"labels": {"sector": "tech", "capsize": "large"}},
    )
    # Bulk upsert with only sector — capsize must persist.
    await client.put(
        "/v1/tickers/AAPL/labels",
        headers=HEADERS,
        json={"labels": {"sector": "consumer"}},
    )
    r = await client.get("/v1/tickers/AAPL/labels", headers=HEADERS)
    keys = {l["key"]: l["value"] for l in r.json()["labels"]}
    assert keys == {"sector": "consumer", "capsize": "large"}


@pytest.mark.asyncio
async def test_delete_label(client):
    await client.put(
        "/v1/tickers/AAPL/labels/sector", headers=HEADERS, json={"value": "tech"}
    )
    r = await client.delete("/v1/tickers/AAPL/labels/sector", headers=HEADERS)
    assert r.status_code == 204
    r2 = await client.delete("/v1/tickers/AAPL/labels/sector", headers=HEADERS)
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_delete_ticker_cascades_labels(client):
    await client.put(
        "/v1/tickers/AAPL/labels/sector", headers=HEADERS, json={"value": "tech"}
    )
    async with _db.SessionLocal() as session:
        ticker = await session.get(Ticker, "AAPL")
        await session.delete(ticker)
        await session.commit()
        rows = (await session.execute(select(TickerLabel))).scalars().all()
    assert rows == []


# ----------------------------------------------------------------------
# Watchlist ?labels= filter
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watchlist_labels_filter_and_logic(client):
    # AAPL: tech + large
    await client.put(
        "/v1/tickers/AAPL/labels",
        headers=HEADERS,
        json={"labels": {"sector": "tech", "capsize": "large"}},
    )
    # MSFT: tech + mid
    await client.put(
        "/v1/tickers/MSFT/labels",
        headers=HEADERS,
        json={"labels": {"sector": "tech", "capsize": "mid"}},
    )
    # NVDA: tech + large
    await client.put(
        "/v1/tickers/NVDA/labels",
        headers=HEADERS,
        json={"labels": {"sector": "tech", "capsize": "large"}},
    )

    # Add all three to watchlist.
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "MSFT"})
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "NVDA"})

    # Filter: sector=tech (all 3)
    r = await client.get(
        "/v1/watchlist", headers=HEADERS, params={"labels": "sector:tech"}
    )
    assert r.json()["count"] == 3

    # Filter: sector=tech AND capsize=large → AAPL + NVDA only
    r = await client.get(
        "/v1/watchlist",
        headers=HEADERS,
        params={"labels": "sector:tech,capsize:large"},
    )
    body = r.json()
    assert body["count"] == 2
    assert {e["symbol"] for e in body["entries"]} == {"AAPL", "NVDA"}

    # Filter: no match → empty
    r = await client.get(
        "/v1/watchlist", headers=HEADERS, params={"labels": "sector:nope"}
    )
    assert r.json()["count"] == 0


@pytest.mark.asyncio
async def test_watchlist_labels_filter_with_bool(client):
    await client.put(
        "/v1/tickers/AAPL/labels/insider_buy", headers=HEADERS, json={"value": True}
    )
    await client.put(
        "/v1/tickers/MSFT/labels/insider_buy", headers=HEADERS, json={"value": False}
    )
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "AAPL"})
    await client.post("/v1/watchlist", headers=HEADERS, json={"symbol": "MSFT"})

    r = await client.get(
        "/v1/watchlist", headers=HEADERS, params={"labels": "insider_buy:true"}
    )
    body = r.json()
    assert body["count"] == 1
    assert body["entries"][0]["symbol"] == "AAPL"
