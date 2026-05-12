"""Earnings calendar — universe, refresh, trigger window, routes."""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core import db as _db
from app.earnings import service as _svc
from app.earnings.models import EarningsCalendarRow
from app.watchlist.models import WatchlistEntry
from app.tickers.models import Ticker

HEADERS = {"X-API-Key": "test-key"}


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


@pytest.fixture
async def seed_roster(client):
    """Seed three tickers in the roster for universe tests."""
    async with _db.SessionLocal() as session:
        for sym in ("AAPL", "META", "NVDA"):
            session.add(Ticker(symbol=sym, asset_class="equity", source="manual"))
        for sym in ("AAPL", "META", "NVDA"):
            session.add(WatchlistEntry(symbol=sym))
        await session.commit()
    yield


@pytest.mark.asyncio
async def test_compute_universe_uses_roster(client, seed_roster, monkeypatch):
    async def _empty_street(snapshots: int = 4):
        return []

    monkeypatch.setattr(_svc, "_street_tickers_recent", _empty_street)
    universe = await _svc.compute_universe()
    assert set(universe) == {"AAPL", "META", "NVDA"}


@pytest.mark.asyncio
async def test_compute_universe_capped_at_150(client, monkeypatch):
    # Empty roster + huge synthetic Street.
    huge = [f"SYM{i:03d}" for i in range(200)]

    async def _huge_street(snapshots: int = 4):
        return huge

    monkeypatch.setattr(_svc, "_street_tickers_recent", _huge_street)
    universe = await _svc.compute_universe()
    assert len(universe) == _svc.UNIVERSE_CAP


@pytest.mark.asyncio
async def test_refresh_for_ticker_yfinance_path(client, monkeypatch, seed_roster):
    next_date = datetime.date.today() + datetime.timedelta(days=21)

    def _yf(_t: str):
        return next_date

    def _no_nasdaq(_t: str):
        return None

    def _no_edgar(_t: str):
        return None

    monkeypatch.setattr(_svc, "_yfinance_next_earnings", _yf)
    monkeypatch.setattr(_svc, "_nasdaq_next_earnings", _no_nasdaq)
    monkeypatch.setattr(_svc, "_edgar_confirm_8k_item_202", _no_edgar)

    result = await _svc.refresh_for_ticker("META")
    assert result["expected_at"] == next_date.isoformat()
    assert result["source"] == "yfinance"

    async with _db.SessionLocal() as session:
        row = await session.get(EarningsCalendarRow, "META")
    assert row is not None
    assert row.expected_at == next_date


@pytest.mark.asyncio
async def test_refresh_for_ticker_falls_back_to_nasdaq(
    client, monkeypatch, seed_roster
):
    fallback = datetime.date.today() + datetime.timedelta(days=10)

    monkeypatch.setattr(_svc, "_yfinance_next_earnings", lambda _t: None)
    monkeypatch.setattr(_svc, "_nasdaq_next_earnings", lambda _t: fallback)
    monkeypatch.setattr(_svc, "_edgar_confirm_8k_item_202", lambda _t: None)

    result = await _svc.refresh_for_ticker("AAPL")
    assert result["source"] == "nasdaq"
    assert result["expected_at"] == fallback.isoformat()


@pytest.mark.asyncio
async def test_refresh_for_ticker_stale_date_treated_as_miss(
    client, monkeypatch, seed_roster
):
    stale = datetime.date.today() - datetime.timedelta(days=15)

    monkeypatch.setattr(_svc, "_yfinance_next_earnings", lambda _t: stale)
    monkeypatch.setattr(_svc, "_nasdaq_next_earnings", lambda _t: None)
    monkeypatch.setattr(_svc, "_edgar_confirm_8k_item_202", lambda _t: None)

    result = await _svc.refresh_for_ticker("NVDA")
    assert result["expected_at"] is None
    assert result["source"] == "miss"


def test_in_trigger_window_within_range():
    expected = datetime.date(2026, 5, 9)
    # Today = expected → True for default window [0, 3].
    fake_now = datetime.datetime(2026, 5, 9, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    assert _svc.in_trigger_window(expected_at=expected, now=fake_now) is True


def test_in_trigger_window_after_expiry():
    expected = datetime.date(2026, 5, 1)
    fake_now = datetime.datetime(2026, 5, 9, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    # 8 days after expected, default window allows only +3.
    assert _svc.in_trigger_window(expected_at=expected, now=fake_now) is False


def test_in_trigger_window_extended_after():
    expected = datetime.date(2026, 5, 1)
    fake_now = datetime.datetime(2026, 5, 6, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    assert (
        _svc.in_trigger_window(
            expected_at=expected, days_before=0, days_after=7, now=fake_now
        )
        is True
    )


def test_channel_trigger_multi_ticker_fires_on_either():
    expected_a = datetime.date(2026, 5, 9)
    fake_now = datetime.datetime(2026, 5, 9, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    cfg = {"tickers": ["GOOGL", "GOOG"], "days_before": 0, "days_after": 3}
    assert (
        _svc.channel_in_trigger_window(
            earnings_trigger=cfg,
            earnings_dates={"GOOGL": expected_a, "GOOG": None},
            now=fake_now,
        )
        is True
    )


def test_channel_trigger_no_dates_returns_false():
    cfg = {"tickers": ["AAPL"], "days_before": 0, "days_after": 3}
    assert (
        _svc.channel_in_trigger_window(
            earnings_trigger=cfg,
            earnings_dates={"AAPL": None},
        )
        is False
    )


@pytest.mark.asyncio
async def test_purge_stale_universe(client):
    long_ago = _utc_now() - datetime.timedelta(days=120)
    recent = _utc_now() - datetime.timedelta(days=30)
    async with _db.SessionLocal() as session:
        session.add(
            EarningsCalendarRow(
                ticker="OLD",
                last_universe_at=long_ago,
                first_seen_at=long_ago,
                updated_at=long_ago,
            )
        )
        session.add(
            EarningsCalendarRow(
                ticker="FRESH",
                last_universe_at=recent,
                first_seen_at=recent,
                updated_at=recent,
            )
        )
        await session.commit()

    purged = await _svc.purge_stale_universe(ttl_days=90)
    assert purged == 1
    async with _db.SessionLocal() as session:
        row_old = await session.get(EarningsCalendarRow, "OLD")
        row_fresh = await session.get(EarningsCalendarRow, "FRESH")
    assert row_old is None
    assert row_fresh is not None


@pytest.mark.asyncio
async def test_upcoming_endpoint(client, seed_roster):
    next_date = datetime.date.today() + datetime.timedelta(days=10)
    async with _db.SessionLocal() as session:
        session.add(
            EarningsCalendarRow(
                ticker="META",
                expected_at=next_date,
                source="yfinance",
                fetched_at=_utc_now(),
            )
        )
        await session.commit()

    r = await client.get("/v1/earnings/upcoming?days=30", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any(item["ticker"] == "META" for item in body["items"])


@pytest.mark.asyncio
async def test_get_one_404_when_missing(client):
    r = await client.get("/v1/earnings/AAPL", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_one_returns_row(client, seed_roster):
    expected = datetime.date.today() + datetime.timedelta(days=20)
    async with _db.SessionLocal() as session:
        session.add(
            EarningsCalendarRow(
                ticker="AAPL",
                expected_at=expected,
                source="yfinance",
                fetched_at=_utc_now(),
            )
        )
        await session.commit()
    r = await client.get("/v1/earnings/AAPL", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["expected_at"] == expected.isoformat()
