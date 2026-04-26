"""Phase 5 — comparison endpoints.

Covers:
- by_target: single (ticker, target_date) drill-down
- by_horizon: multi-ticker grid for target_date × horizons
- ?fields= preset + CSV
- ?made_on_dow= filter
- Missing data graceful (actual=null, prediction=null)
"""
from __future__ import annotations

import datetime

import pytest

from app.analysis.models import AnalysisJob, AnalysisTask
from app.core import db as _db
from app.market_data.models import OhlcvBar
from app.predictions import comparison, service as predictions_svc

HEADERS = {"X-API-Key": "test-key"}


def _bar(close: float, ts: datetime.datetime) -> dict:
    return {
        "ts": ts.isoformat(),
        "open": close - 1, "high": close + 1, "low": close - 2,
        "close": close, "volume": 1000.0, "amount": 0.0,
    }


async def _seed_run(
    *,
    job_id: str,
    task_id: str,
    ticker: str,
    made_on: datetime.date,
    forecast_targets: list[tuple[datetime.date, float]],
    model_id: str = "kronos_base",
):
    """Helper: create a done task + explode into prediction_points."""
    started = datetime.datetime.combine(
        made_on, datetime.time(12, 0, tzinfo=datetime.timezone.utc)
    )
    forecast = [
        _bar(close, datetime.datetime.combine(d, datetime.time(0, 0, tzinfo=datetime.timezone.utc)))
        for d, close in forecast_targets
    ]
    async with _db.SessionLocal() as session:
        session.add(
            AnalysisJob(
                id=job_id, status="done", inputs_json={}, task_count=1,
                origin="self", submitted_at=started,
            )
        )
        session.add(
            AnalysisTask(
                id=task_id, job_id=job_id, ticker=ticker, interval="1d",
                model_id=model_id, status="done",
                started_at=started, finished_at=started,
                result_json={"forecast": forecast, "model_id": model_id, "horizon_bars": len(forecast)},
            )
        )
        await session.commit()
    await predictions_svc.explode_task(task_id)


async def _seed_actual(
    *, ticker: str, target_date: datetime.date, close: float
):
    ts = datetime.datetime.combine(
        target_date, datetime.time(0, 0, tzinfo=datetime.timezone.utc)
    )
    async with _db.SessionLocal() as session:
        session.add(
            OhlcvBar(
                symbol=ticker, interval="1d", ts=ts,
                open=close - 1, high=close + 1, low=close - 2, close=close,
                volume=1000.0, amount=0.0, provider="test",
            )
        )
        await session.commit()


# ----------------------------------------------------------------------
# Field selector
# ----------------------------------------------------------------------

def test_parse_fields_default():
    assert comparison.parse_fields(None) == ("open", "high", "low", "close", "volume")


def test_parse_fields_preset():
    assert comparison.parse_fields("ohlc") == ("open", "high", "low", "close")
    assert comparison.parse_fields("c") == ("close",)
    assert comparison.parse_fields("all") == ("open", "high", "low", "close", "volume", "amount")


def test_parse_fields_csv():
    assert comparison.parse_fields("close,high") == ("close", "high")
    assert comparison.parse_fields("close, high ,low") == ("close", "high", "low")


def test_parse_fields_drops_invalid():
    assert comparison.parse_fields("close,bogus,high") == ("close", "high")


def test_parse_fields_empty_falls_back():
    # All garbage → default
    assert comparison.parse_fields("xx,yy") == ("open", "high", "low", "close", "volume")


def test_parse_dow_filter():
    assert comparison.parse_dow_filter(None) is None
    assert comparison.parse_dow_filter("4") == (4,)
    assert comparison.parse_dow_filter("0,4") == (0, 4)
    assert comparison.parse_dow_filter("0,4,4") == (0, 4)  # de-dup
    assert comparison.parse_dow_filter("9,4") == (4,)  # out-of-range dropped
    assert comparison.parse_dow_filter("garbage") is None


# ----------------------------------------------------------------------
# by_target
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_by_target_returns_predictions_and_actual(client):
    target = datetime.date(2026, 5, 2)
    # 4 runs predicting 2026-05-02, made on 4 successive days.
    for days_ago in range(1, 5):
        made_on = target - datetime.timedelta(days=days_ago)
        await _seed_run(
            job_id=f"j-{days_ago}", task_id=f"t-{days_ago}",
            ticker="AAPL", made_on=made_on,
            forecast_targets=[(target, 100 + days_ago)],
        )
    # Actual close 105.
    await _seed_actual(ticker="AAPL", target_date=target, close=105.0)

    r = await client.get(
        "/v1/predictions/by-target",
        headers=HEADERS,
        params={"ticker": "AAPL", "target_date": "2026-05-02"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["target_date"] == "2026-05-02"
    assert body["actual"] is not None
    assert body["actual"]["close"] == 105.0
    assert len(body["predictions"]) == 4
    # Sorted made_on DESC.
    days_ago_in_response = [p["days_ago"] for p in body["predictions"]]
    assert days_ago_in_response == sorted(days_ago_in_response)


@pytest.mark.asyncio
async def test_by_target_actual_null_when_missing(client):
    target = datetime.date(2026, 5, 2)
    made_on = target - datetime.timedelta(days=1)
    await _seed_run(
        job_id="j", task_id="t", ticker="AAPL", made_on=made_on,
        forecast_targets=[(target, 100.0)],
    )
    # No actual seeded.
    r = await client.get(
        "/v1/predictions/by-target", headers=HEADERS,
        params={"ticker": "AAPL", "target_date": "2026-05-02"},
    )
    body = r.json()
    assert body["actual"] is None
    assert len(body["predictions"]) == 1


@pytest.mark.asyncio
async def test_by_target_fields_filter_close_only(client):
    target = datetime.date(2026, 5, 2)
    await _seed_run(
        job_id="j", task_id="t", ticker="AAPL",
        made_on=target - datetime.timedelta(days=1),
        forecast_targets=[(target, 100.0)],
    )
    await _seed_actual(ticker="AAPL", target_date=target, close=105.0)

    r = await client.get(
        "/v1/predictions/by-target", headers=HEADERS,
        params={"ticker": "AAPL", "target_date": "2026-05-02", "fields": "close"},
    )
    body = r.json()
    assert body["fields"] == ["close"]
    assert "open" not in body["actual"]
    assert "high" not in body["predictions"][0]
    assert body["predictions"][0]["close"] == 100.0
    assert body["actual"]["close"] == 105.0


@pytest.mark.asyncio
async def test_by_target_fields_csv(client):
    target = datetime.date(2026, 5, 2)
    await _seed_run(
        job_id="j", task_id="t", ticker="AAPL",
        made_on=target - datetime.timedelta(days=1),
        forecast_targets=[(target, 100.0)],
    )
    r = await client.get(
        "/v1/predictions/by-target", headers=HEADERS,
        params={"ticker": "AAPL", "target_date": "2026-05-02", "fields": "high,low"},
    )
    body = r.json()
    assert set(body["fields"]) == {"high", "low"}
    p = body["predictions"][0]
    assert "high" in p and "low" in p
    assert "close" not in p


@pytest.mark.asyncio
async def test_by_target_made_on_dow_filter(client):
    target = datetime.date(2026, 5, 2)  # Saturday — pretend
    # Seed predictions made on different weekdays.
    # Made 2026-04-28 (Tue=1) and 2026-04-29 (Wed=2)
    await _seed_run(
        job_id="ja", task_id="ta", ticker="AAPL",
        made_on=datetime.date(2026, 4, 28),  # Tue
        forecast_targets=[(target, 100.0)],
    )
    await _seed_run(
        job_id="jb", task_id="tb", ticker="AAPL",
        made_on=datetime.date(2026, 4, 29),  # Wed
        forecast_targets=[(target, 101.0)],
    )

    # Filter to Wednesday only.
    r = await client.get(
        "/v1/predictions/by-target", headers=HEADERS,
        params={"ticker": "AAPL", "target_date": "2026-05-02", "made_on_dow": "2"},
    )
    body = r.json()
    assert len(body["predictions"]) == 1
    assert body["predictions"][0]["made_on_dow"] == 2
    assert body["predictions"][0]["close"] == 101.0


@pytest.mark.asyncio
async def test_by_target_model_id_filter(client):
    target = datetime.date(2026, 5, 2)
    made_on = target - datetime.timedelta(days=1)
    await _seed_run(
        job_id="ja", task_id="ta", ticker="AAPL", made_on=made_on,
        forecast_targets=[(target, 100.0)], model_id="kronos_base",
    )
    await _seed_run(
        job_id="jb", task_id="tb", ticker="AAPL", made_on=made_on,
        forecast_targets=[(target, 101.0)], model_id="kronos_small",
    )

    r = await client.get(
        "/v1/predictions/by-target", headers=HEADERS,
        params={"ticker": "AAPL", "target_date": "2026-05-02", "model_id": "kronos_small"},
    )
    body = r.json()
    assert len(body["predictions"]) == 1
    assert body["predictions"][0]["model_id"] == "kronos_small"


# ----------------------------------------------------------------------
# by_horizon
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_by_horizon_grid(client):
    target = datetime.date(2026, 5, 5)
    # AAPL: predictions made 1d, 3d, 5d before target.
    for h in (1, 3, 5):
        made_on = target - datetime.timedelta(days=h)
        await _seed_run(
            job_id=f"ja-{h}", task_id=f"ta-{h}", ticker="AAPL",
            made_on=made_on, forecast_targets=[(target, 200 + h)],
        )
    # MSFT: only h=2.
    await _seed_run(
        job_id="jm", task_id="tm", ticker="MSFT",
        made_on=target - datetime.timedelta(days=2),
        forecast_targets=[(target, 300.0)],
    )
    await _seed_actual(ticker="AAPL", target_date=target, close=210.0)
    await _seed_actual(ticker="MSFT", target_date=target, close=305.0)

    r = await client.get(
        "/v1/predictions/by-horizon", headers=HEADERS,
        params={
            "target_date": "2026-05-05",
            "horizons": "1,2,3,4,5",
            "tickers": "AAPL,MSFT",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    rows = body["rows"]
    # 2 tickers × 5 horizons = 10 cells
    assert len(rows) == 10
    # AAPL h=1 has prediction; h=2 missing
    aapl_1 = [r for r in rows if r["ticker"] == "AAPL" and r["days_ago"] == 1][0]
    aapl_2 = [r for r in rows if r["ticker"] == "AAPL" and r["days_ago"] == 2][0]
    assert aapl_1["prediction"] is not None
    assert aapl_1["prediction"]["close"] == 201.0
    assert aapl_2["prediction"] is None
    assert aapl_1["actual"]["close"] == 210.0


@pytest.mark.asyncio
async def test_by_horizon_with_dow_filter(client):
    target = datetime.date(2026, 5, 5)
    # h=1 means made_on=2026-05-04 (Mon=0); h=2 means 2026-05-03 (Sun=6).
    for h in (1, 2):
        await _seed_run(
            job_id=f"j-{h}", task_id=f"t-{h}", ticker="AAPL",
            made_on=target - datetime.timedelta(days=h),
            forecast_targets=[(target, 100 + h)],
        )
    # Filter to weekdays only (Mon-Fri = 0-4) — should drop Sun (h=2).
    r = await client.get(
        "/v1/predictions/by-horizon", headers=HEADERS,
        params={
            "target_date": "2026-05-05",
            "horizons": "1,2",
            "tickers": "AAPL",
            "made_on_dow": "0,1,2,3,4",
        },
    )
    body = r.json()
    rows = body["rows"]
    h1 = [r for r in rows if r["days_ago"] == 1][0]
    h2 = [r for r in rows if r["days_ago"] == 2][0]
    assert h1["prediction"] is not None  # Monday — kept
    assert h2["prediction"] is None  # Sunday — filtered


@pytest.mark.asyncio
async def test_by_horizon_400_on_bad_horizons(client):
    r = await client.get(
        "/v1/predictions/by-horizon", headers=HEADERS,
        params={"target_date": "2026-05-05", "horizons": "abc", "tickers": "AAPL"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_by_horizon_400_on_empty_tickers(client):
    r = await client.get(
        "/v1/predictions/by-horizon", headers=HEADERS,
        params={"target_date": "2026-05-05", "horizons": "1", "tickers": ""},
    )
    assert r.status_code in (400, 422)
