"""Macro Workbench M-1 — service + route tests.

Strategy: monkey-patch the providers so no test ever hits yfinance or
FRED over the network. Asserts on the cached state + the routes' JSON
contracts.
"""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from app.macro import registry as macro_registry
from app.macro import service as macro_service
from app.macro.providers.fred_provider import FREDProvider
from app.macro.providers.yfinance_provider import YFinanceMacroProvider

HEADERS = {"X-API-Key": "test-key"}


# ----------------------------------------------------------------------
# Fixtures — block real network + control the registry per test.
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _block_real_providers(monkeypatch):
    """Both providers replaced with empty fetchers by default. Tests that
    want data monkey-patch again locally.
    """
    async def _empty(self, symbol, since=None):
        return []

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", _empty)
    monkeypatch.setattr(FREDProvider, "fetch", _empty)


@pytest.fixture
def tiny_registry(tmp_path: Path, monkeypatch):
    """Registry with two symbols (one yf, one fred) for fan-out tests."""
    p = tmp_path / "registry.yaml"
    p.write_text(
        """
yfinance:
  - symbol: "TEST_YF"
fred:
  - id: "TEST_FRED"
"""
    )
    macro_registry.reset_cache()
    monkeypatch.setattr(macro_registry, "_REGISTRY_PATH", p)
    yield p
    macro_registry.reset_cache()


# ----------------------------------------------------------------------
# Service: upsert + idempotency
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_upserts_points(client, monkeypatch, tiny_registry):
    points = [
        (datetime.date(2026, 4, 1), 100.0),
        (datetime.date(2026, 4, 2), 101.0),
        (datetime.date(2026, 4, 3), 102.0),
    ]

    async def fake_fetch(self, symbol, since=None):
        return points

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", fake_fetch)

    n = await macro_service.refresh("TEST_YF")
    assert n == 3

    # Read back via service.get_series.
    rows = await macro_service.get_series(
        "TEST_YF", since=datetime.date(2026, 4, 1)
    )
    assert [(r["ts"], r["value"]) for r in rows] == points


@pytest.mark.asyncio
async def test_refresh_idempotent(client, monkeypatch, tiny_registry):
    """Re-running refresh produces the same row count, not duplicates."""
    points = [(datetime.date(2026, 4, 1), 100.0)]

    async def fake_fetch(self, symbol, since=None):
        return points

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", fake_fetch)

    await macro_service.refresh("TEST_YF")
    await macro_service.refresh("TEST_YF")

    rows = await macro_service.get_series(
        "TEST_YF", since=datetime.date(2026, 4, 1)
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_refresh_updates_changed_value(client, monkeypatch, tiny_registry):
    """Same (symbol, ts) with a different value → row updated, not duplicated."""

    async def first_fetch(self, symbol, since=None):
        return [(datetime.date(2026, 4, 1), 100.0)]

    async def revised_fetch(self, symbol, since=None):
        return [(datetime.date(2026, 4, 1), 105.0)]

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", first_fetch)
    await macro_service.refresh("TEST_YF")

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", revised_fetch)
    await macro_service.refresh("TEST_YF")

    rows = await macro_service.get_series(
        "TEST_YF", since=datetime.date(2026, 4, 1)
    )
    assert len(rows) == 1
    assert rows[0]["value"] == 105.0


@pytest.mark.asyncio
async def test_refresh_chunks_large_payloads(client, monkeypatch, tiny_registry):
    """Regression: yfinance can return >10k daily bars for old tickers
    which blows past Postgres' 32767 bind-parameter limit on a single
    INSERT. _upsert_points must chunk."""
    big_payload = [
        (datetime.date(2000, 1, 1) + datetime.timedelta(days=i), float(i))
        for i in range(5000)
    ]

    async def fake_fetch(self, symbol, since=None):
        return big_payload

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", fake_fetch)
    n = await macro_service.refresh("TEST_YF")
    assert n == 5000

    rows = await macro_service.get_series(
        "TEST_YF", since=datetime.date(2000, 1, 1)
    )
    assert len(rows) == 5000


@pytest.mark.asyncio
async def test_refresh_unknown_symbol_raises(client, tiny_registry):
    with pytest.raises(ValueError, match="not in macro registry"):
        await macro_service.refresh("NOT_IN_REGISTRY")


# ----------------------------------------------------------------------
# Service: get_series filters
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_series_filters_by_window(client, monkeypatch, tiny_registry):
    async def fake_fetch(self, symbol, since=None):
        return [
            (datetime.date(2026, 1, d), float(d)) for d in (10, 15, 20, 25, 30)
        ]

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", fake_fetch)
    await macro_service.refresh("TEST_YF")

    rows = await macro_service.get_series(
        "TEST_YF",
        since=datetime.date(2026, 1, 15),
        until=datetime.date(2026, 1, 25),
    )
    assert [r["ts"].day for r in rows] == [15, 20, 25]


# ----------------------------------------------------------------------
# Service: compute_ratio
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_ratio_inner_joins_on_date(
    client, monkeypatch, tiny_registry
):
    """Ratio only emits where BOTH symbols have a value for that date."""

    async def yf_fetch(self, symbol, since=None):
        return [
            (datetime.date(2026, 4, 1), 200.0),
            (datetime.date(2026, 4, 2), 210.0),
            (datetime.date(2026, 4, 3), 220.0),
        ]

    async def fred_fetch(self, symbol, since=None):
        return [
            (datetime.date(2026, 4, 1), 100.0),
            # 4/2 missing — should NOT appear in ratio
            (datetime.date(2026, 4, 3), 110.0),
        ]

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", yf_fetch)
    monkeypatch.setattr(FREDProvider, "fetch", fred_fetch)
    await macro_service.refresh("TEST_YF")
    await macro_service.refresh("TEST_FRED")

    ratio = await macro_service.compute_ratio(
        numerator="TEST_YF",
        denominator="TEST_FRED",
        since=datetime.date(2026, 4, 1),
    )
    assert [r["ts"].day for r in ratio] == [1, 3]
    assert ratio[0]["value"] == pytest.approx(2.0)   # 200 / 100
    assert ratio[1]["value"] == pytest.approx(2.0)   # 220 / 110


@pytest.mark.asyncio
async def test_compute_ratio_skips_zero_denominator(
    client, monkeypatch, tiny_registry
):
    async def yf_fetch(self, symbol, since=None):
        return [(datetime.date(2026, 4, 1), 200.0)]

    async def fred_fetch(self, symbol, since=None):
        return [(datetime.date(2026, 4, 1), 0.0)]

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", yf_fetch)
    monkeypatch.setattr(FREDProvider, "fetch", fred_fetch)
    await macro_service.refresh("TEST_YF")
    await macro_service.refresh("TEST_FRED")

    ratio = await macro_service.compute_ratio(
        numerator="TEST_YF",
        denominator="TEST_FRED",
        since=datetime.date(2026, 4, 1),
    )
    assert ratio == []  # division by zero correctly skipped


# ----------------------------------------------------------------------
# Service: refresh_all
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_all_walks_registry(client, monkeypatch, tiny_registry):
    yf_calls: list[str] = []
    fred_calls: list[str] = []

    async def yf_fetch(self, symbol, since=None):
        yf_calls.append(symbol)
        return [(datetime.date(2026, 4, 1), 1.0)]

    async def fred_fetch(self, symbol, since=None):
        fred_calls.append(symbol)
        return [(datetime.date(2026, 4, 1), 2.0)]

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", yf_fetch)
    monkeypatch.setattr(FREDProvider, "fetch", fred_fetch)

    stats = await macro_service.refresh_all()

    assert yf_calls == ["TEST_YF"]
    assert fred_calls == ["TEST_FRED"]
    assert stats["ok"] == 2
    assert stats["failed"] == 0
    assert stats["rows_touched"] == 2


@pytest.mark.asyncio
async def test_refresh_all_continues_on_provider_error(
    client, monkeypatch, tiny_registry
):
    async def yf_boom(self, symbol, since=None):
        raise RuntimeError("yfinance hiccup")

    async def fred_ok(self, symbol, since=None):
        return [(datetime.date(2026, 4, 1), 2.0)]

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", yf_boom)
    monkeypatch.setattr(FREDProvider, "fetch", fred_ok)

    stats = await macro_service.refresh_all()

    assert stats["failed"] == 1
    assert stats["ok"] == 1
    assert any("TEST_YF" in f for f in stats["failures"])


# ----------------------------------------------------------------------
# Routes — round-trip JSON contracts
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_get_series_returns_payload(
    client, monkeypatch, tiny_registry
):
    async def yf_fetch(self, symbol, since=None):
        return [
            (datetime.date(2026, 4, 1), 100.0),
            (datetime.date(2026, 4, 2), 101.0),
        ]

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", yf_fetch)
    await macro_service.refresh("TEST_YF")

    r = await client.get(
        "/v1/macro/series?symbol=TEST_YF&since=2026-04-01", headers=HEADERS
    )
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "TEST_YF"
    assert len(body["points"]) == 2
    assert body["points"][0]["value"] == 100.0


@pytest.mark.asyncio
async def test_route_compute_ratio_round_trip(
    client, monkeypatch, tiny_registry
):
    async def yf_fetch(self, symbol, since=None):
        return [(datetime.date(2026, 4, 1), 200.0)]

    async def fred_fetch(self, symbol, since=None):
        return [(datetime.date(2026, 4, 1), 100.0)]

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", yf_fetch)
    monkeypatch.setattr(FREDProvider, "fetch", fred_fetch)
    await macro_service.refresh("TEST_YF")
    await macro_service.refresh("TEST_FRED")

    r = await client.get(
        "/v1/macro/ratio?numerator=TEST_YF&denominator=TEST_FRED"
        "&since=2026-04-01",
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["numerator"] == "TEST_YF"
    assert body["denominator"] == "TEST_FRED"
    assert body["points"] == [{"ts": "2026-04-01", "value": 2.0}]


@pytest.mark.asyncio
async def test_route_refresh_all(client, monkeypatch, tiny_registry):
    async def fake_fetch(self, symbol, since=None):
        return [(datetime.date(2026, 4, 1), 1.0)]

    monkeypatch.setattr(YFinanceMacroProvider, "fetch", fake_fetch)
    monkeypatch.setattr(FREDProvider, "fetch", fake_fetch)

    r = await client.post("/v1/macro/refresh", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] == 2
    assert body["failed"] == 0


@pytest.mark.asyncio
async def test_route_refresh_unknown_symbol_400(client, tiny_registry):
    r = await client.post(
        "/v1/macro/refresh?symbol=NOPE_NOT_THERE", headers=HEADERS
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_route_refresh_requires_auth(client, tiny_registry):
    r = await client.post("/v1/macro/refresh")
    assert r.status_code in (401, 403)


# ----------------------------------------------------------------------
# Provider: FRED CSV parser
# ----------------------------------------------------------------------


def test_fred_csv_parser_drops_dot_observations():
    """FRED uses '.' for missing values; parser must drop them."""
    from app.macro.providers.fred_provider import _parse_fred_csv

    body = (
        "DATE,WALCL\n"
        "2026-04-01,8200000\n"
        "2026-04-08,.\n"          # missing obs — drop
        "2026-04-15,8210000\n"
        ",100\n"                  # malformed — drop
        "bad-date,5\n"            # malformed — drop
    )
    out = _parse_fred_csv("WALCL", body)
    assert out == [
        (datetime.date(2026, 4, 1), 8200000.0),
        (datetime.date(2026, 4, 15), 8210000.0),
    ]
