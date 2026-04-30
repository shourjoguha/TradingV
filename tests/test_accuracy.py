"""Accuracy evaluator + math + idempotency tests — Phase 1.1.

Strategy:
- Build a tiny world: AnalysisJob → AnalysisTask → PredictionPoint(s) +
  matching OhlcvBar(s). Run :func:`evaluate_pending`. Assert per-row math
  + aggregations match expectations.
- No real HTTP. No real provider calls. Pure DB.
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from app.accuracy import service as accuracy_service
from app.accuracy.models import PredictionAccuracy
from app.core import db as _db
from app.market_data.models import OhlcvBar
from app.predictions.models import PredictionPoint

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def _stub_md_refresh(monkeypatch):
    """The accuracy evaluator now calls md_service.refresh when actuals
    are missing. Stub it so the suite never hits yfinance over the
    network. Tests that want to assert refresh-call behavior monkeypatch
    again locally."""
    from app.market_data import service as md_service

    async def _noop(*_a, **_kw):
        return 0

    monkeypatch.setattr(md_service, "refresh", _noop)


# ----------------------------------------------------------------------
# Helpers — bypass the analysis pipeline; insert raw rows.
# ----------------------------------------------------------------------


async def _insert_prediction(
    *,
    ticker: str,
    interval: str,
    made_on: datetime.date,
    target_ts: datetime.datetime,
    horizon_offset: int,
    predicted_close: float,
    model_id: str = "kronos-base",
    task_id: str | None = None,
) -> str:
    """Bypass FK to analysis_tasks (SQLite doesn't enforce by default; tests
    care about prediction_accuracy joins, not analysis_tasks integrity)."""
    pp = PredictionPoint(
        task_id=task_id or f"task-{ticker}-{horizon_offset}",
        ticker=ticker,
        model_id=model_id,
        interval=interval,
        made_on=made_on,
        made_on_dow=made_on.weekday(),
        target_date=target_ts.date(),
        target_ts=target_ts,
        horizon_offset=horizon_offset,
        open=predicted_close,
        high=predicted_close,
        low=predicted_close,
        close=predicted_close,
    )
    async with _db.SessionLocal() as s:
        # Disable FK on this connection only — analysis_tasks doesn't exist
        # in our minimal fixture for accuracy-focused tests.
        await s.execute(__import__("sqlalchemy").text("PRAGMA foreign_keys=OFF"))
        s.add(pp)
        await s.commit()
    return pp.id


async def _insert_actual(
    *, ticker: str, interval: str, ts: datetime.datetime, close: float
) -> None:
    bar = OhlcvBar(
        symbol=ticker,
        interval=interval,
        ts=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0,
        amount=0,
        provider="test",
    )
    async with _db.SessionLocal() as s:
        s.add(bar)
        await s.commit()


# ----------------------------------------------------------------------
# Pure-math unit tests
# ----------------------------------------------------------------------


def test_compute_metrics_basic():
    m = accuracy_service._compute_metrics(
        predicted_close=98.0, actual_close=100.0, baseline_close=95.0
    )
    assert m["error_pct"] == pytest.approx(0.02)
    assert m["abs_error_pct"] == pytest.approx(0.02)
    assert m["squared_error"] == pytest.approx(4.0)
    # Predicted moved up from 95→98 (+3); actual moved up from 95→100 (+5). Same direction.
    assert m["direction_correct"] is True


def test_compute_metrics_direction_wrong():
    m = accuracy_service._compute_metrics(
        predicted_close=110.0, actual_close=90.0, baseline_close=100.0
    )
    # Predicted UP (+10), actual DOWN (-10) → wrong call.
    assert m["direction_correct"] is False
    assert m["error_pct"] == pytest.approx(-20.0 / 90.0)
    assert m["abs_error_pct"] == pytest.approx(20.0 / 90.0)


def test_compute_metrics_no_baseline_means_null_direction():
    m = accuracy_service._compute_metrics(
        predicted_close=100.0, actual_close=100.0, baseline_close=None
    )
    assert m["direction_correct"] is None


def test_compute_metrics_zero_actual_returns_empty():
    # Division-by-zero / non-physical — skip.
    assert accuracy_service._compute_metrics(
        predicted_close=10.0, actual_close=0.0, baseline_close=5.0
    ) == {}


def test_compute_metrics_flat_baseline_both_flat():
    m = accuracy_service._compute_metrics(
        predicted_close=100.0, actual_close=100.0, baseline_close=100.0
    )
    # Both flat = trivially correct.
    assert m["direction_correct"] is True


def test_compute_metrics_flat_one_side_only():
    # Predicted no movement, but actual moved → wrong directional call.
    m = accuracy_service._compute_metrics(
        predicted_close=100.0, actual_close=105.0, baseline_close=100.0
    )
    assert m["direction_correct"] is False


# ----------------------------------------------------------------------
# Evaluator integration tests
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_pending_inserts_row_when_actual_present(client):
    made_on = datetime.date(2026, 4, 20)
    target_ts = datetime.datetime(2026, 4, 21, 0, 0, 0, tzinfo=datetime.timezone.utc)
    baseline_ts = datetime.datetime(2026, 4, 20, 0, 0, 0, tzinfo=datetime.timezone.utc)

    pred_id = await _insert_prediction(
        ticker="AAPL",
        interval="1d",
        made_on=made_on,
        target_ts=target_ts,
        horizon_offset=1,
        predicted_close=180.0,
    )
    await _insert_actual(ticker="AAPL", interval="1d", ts=target_ts, close=183.0)
    await _insert_actual(ticker="AAPL", interval="1d", ts=baseline_ts, close=178.0)

    now = datetime.datetime(2026, 4, 22, tzinfo=datetime.timezone.utc)
    stats = await accuracy_service.evaluate_pending(now=now)

    assert stats == {
        "scanned": 1,
        "evaluated": 1,
        "skipped_no_actual": 0,
        "skipped_bad_data": 0,
        "ohlcv_refreshed": 0,
    }

    async with _db.SessionLocal() as s:
        row = (await s.execute(select(PredictionAccuracy))).scalar_one()
        assert row.prediction_id == pred_id
        assert row.predicted_close == 180.0
        assert row.actual_close == 183.0
        assert row.baseline_close == 178.0
        # Predicted UP (+2), actual UP (+5) → direction correct.
        assert row.direction_correct is True
        assert row.error_pct == pytest.approx((183 - 180) / 183)


@pytest.mark.asyncio
async def test_evaluate_pending_skips_when_no_actual(client):
    made_on = datetime.date(2026, 4, 20)
    target_ts = datetime.datetime(2026, 4, 21, 0, 0, 0, tzinfo=datetime.timezone.utc)

    await _insert_prediction(
        ticker="MSFT",
        interval="1d",
        made_on=made_on,
        target_ts=target_ts,
        horizon_offset=1,
        predicted_close=400.0,
    )
    # No actual inserted.

    now = datetime.datetime(2026, 4, 22, tzinfo=datetime.timezone.utc)
    stats = await accuracy_service.evaluate_pending(now=now)

    assert stats["evaluated"] == 0
    assert stats["skipped_no_actual"] == 1

    async with _db.SessionLocal() as s:
        rows = (await s.execute(select(PredictionAccuracy))).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_evaluate_pending_skips_future_predictions(client):
    """Predictions whose target_ts > now should not be considered."""
    made_on = datetime.date(2026, 4, 25)
    future_target = datetime.datetime(2026, 5, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)

    await _insert_prediction(
        ticker="NVDA",
        interval="1d",
        made_on=made_on,
        target_ts=future_target,
        horizon_offset=5,
        predicted_close=1000.0,
    )

    now = datetime.datetime(2026, 4, 26, tzinfo=datetime.timezone.utc)
    stats = await accuracy_service.evaluate_pending(now=now)

    assert stats["scanned"] == 0


@pytest.mark.asyncio
async def test_evaluate_pending_idempotent(client):
    """Running twice produces the same single row, not duplicates."""
    made_on = datetime.date(2026, 4, 20)
    target_ts = datetime.datetime(2026, 4, 21, 0, 0, 0, tzinfo=datetime.timezone.utc)

    await _insert_prediction(
        ticker="GOOG",
        interval="1d",
        made_on=made_on,
        target_ts=target_ts,
        horizon_offset=1,
        predicted_close=170.0,
    )
    await _insert_actual(ticker="GOOG", interval="1d", ts=target_ts, close=170.0)

    now = datetime.datetime(2026, 4, 22, tzinfo=datetime.timezone.utc)
    s1 = await accuracy_service.evaluate_pending(now=now)
    s2 = await accuracy_service.evaluate_pending(now=now)

    assert s1["evaluated"] == 1
    assert s2["evaluated"] == 0  # Already done, won't re-evaluate.

    async with _db.SessionLocal() as s:
        rows = (await s.execute(select(PredictionAccuracy))).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_accuracy_grid_aggregates_correctly(client):
    """Three predictions for the same (ticker, horizon) → one grid row with
    correct MAPE, RMSE, hit-rate."""
    base_ts = datetime.datetime(2026, 4, 21, 0, 0, 0, tzinfo=datetime.timezone.utc)

    # Three predictions for AAPL@1d, all with baseline 100, varying outcomes.
    # Spaced 5 days apart so baseline and actual ts never collide.
    cases = [
        # predicted, actual
        (102.0, 105.0),  # both up; correct dir
        (108.0, 105.0),  # both up; correct dir
        (90.0, 105.0),   # predicted DOWN, actual UP; wrong dir
    ]
    for i, (pred_close, actual_close) in enumerate(cases):
        ts = base_ts + datetime.timedelta(days=i * 5)
        baseline_ts = ts - datetime.timedelta(days=1)
        await _insert_prediction(
            ticker="AAPL",
            interval="1d",
            made_on=baseline_ts.date(),
            target_ts=ts,
            horizon_offset=1,
            predicted_close=pred_close,
            task_id=f"task-{i}",
        )
        await _insert_actual(ticker="AAPL", interval="1d", ts=ts, close=actual_close)
        await _insert_actual(ticker="AAPL", interval="1d", ts=baseline_ts, close=100.0)

    now = base_ts + datetime.timedelta(days=10)
    await accuracy_service.evaluate_pending(now=now)

    grid = await accuracy_service.accuracy_grid()
    assert len(grid) == 1
    g = grid[0]
    assert g["ticker"] == "AAPL"
    assert g["horizon_offset"] == 1
    assert g["sample_count"] == 3
    # MAPE = mean of |error_pct|; verify within a percent.
    expected_mape = (
        abs((105 - 102) / 105) + abs((105 - 108) / 105) + abs((105 - 90) / 105)
    ) / 3
    assert g["mape"] == pytest.approx(expected_mape)
    # RMSE = sqrt(mean((actual-pred)^2))
    expected_rmse = ((9 + 9 + 225) / 3) ** 0.5
    assert g["rmse"] == pytest.approx(expected_rmse)
    # 2 of 3 directions correct.
    assert g["hit_rate"] == pytest.approx(2 / 3)


# ----------------------------------------------------------------------
# Route smoke tests
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_route_returns_stats(client):
    r = await client.post("/v1/accuracy/evaluate", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "scanned",
        "evaluated",
        "skipped_no_actual",
        "skipped_bad_data",
        "ohlcv_refreshed",
    }


@pytest.mark.asyncio
async def test_grid_route_empty(client):
    r = await client.get("/v1/accuracy/grid", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body == {"rows": [], "window_size": 30}


@pytest.mark.asyncio
async def test_pair_route_empty(client):
    r = await client.get(
        "/v1/accuracy/pair?ticker=AAPL&horizon_offset=1", headers=HEADERS
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"ticker": "AAPL", "horizon_offset": 1, "rows": []}


@pytest.mark.asyncio
async def test_evaluate_requires_auth(client):
    r = await client.post("/v1/accuracy/evaluate")
    assert r.status_code in (401, 403)


# ----------------------------------------------------------------------
# Interval filter — keeps 1h and 1d cadences in separate buckets.
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accuracy_grid_separates_intervals(client):
    """A ticker with both 1d and 1h evaluations must yield two grid rows
    (one per interval), not one row that averages them together."""
    base_ts = datetime.datetime(2026, 4, 21, 0, 0, 0, tzinfo=datetime.timezone.utc)

    # 1d row: predicted 102, actual 105.
    await _insert_prediction(
        ticker="AAPL", interval="1d",
        made_on=(base_ts - datetime.timedelta(days=1)).date(),
        target_ts=base_ts, horizon_offset=1, predicted_close=102.0, task_id="task-d",
    )
    await _insert_actual(ticker="AAPL", interval="1d", ts=base_ts, close=105.0)
    await _insert_actual(
        ticker="AAPL", interval="1d",
        ts=base_ts - datetime.timedelta(days=1), close=100.0,
    )

    # 1h row: predicted 200, actual 202 — different magnitudes so we can tell
    # the two grid rows apart.
    h_target = base_ts + datetime.timedelta(hours=1)
    await _insert_prediction(
        ticker="AAPL", interval="1h",
        made_on=base_ts.date(),
        target_ts=h_target, horizon_offset=1, predicted_close=200.0, task_id="task-h",
    )
    await _insert_actual(ticker="AAPL", interval="1h", ts=h_target, close=202.0)
    await _insert_actual(ticker="AAPL", interval="1h", ts=base_ts, close=199.0)

    now = base_ts + datetime.timedelta(days=2)
    await accuracy_service.evaluate_pending(now=now)

    # No filter: two grid rows (1d + 1h), same ticker+horizon but distinct intervals.
    grid_all = await accuracy_service.accuracy_grid()
    intervals = sorted(g["interval"] for g in grid_all)
    assert intervals == ["1d", "1h"]
    assert all(g["sample_count"] == 1 for g in grid_all)

    # Filter 1d → only the 1d row.
    grid_d = await accuracy_service.accuracy_grid(interval="1d")
    assert len(grid_d) == 1
    assert grid_d[0]["interval"] == "1d"

    # Filter 1h → only the 1h row.
    grid_h = await accuracy_service.accuracy_grid(interval="1h")
    assert len(grid_h) == 1
    assert grid_h[0]["interval"] == "1h"


@pytest.mark.asyncio
async def test_evaluator_triggers_ohlcv_refresh_when_actual_missing(client, monkeypatch):
    """When the bar isn't in cache, the evaluator should ask the provider
    to refresh once per (ticker, interval) per tick and re-check."""
    from app.market_data import service as md_service

    calls: list[tuple[str, str]] = []

    async def tracking_refresh(symbol, interval, **_kw):
        calls.append((symbol, interval))
        return 0

    monkeypatch.setattr(md_service, "refresh", tracking_refresh)

    made_on = datetime.date(2026, 4, 20)
    target_ts = datetime.datetime(2026, 4, 21, 0, 0, 0, tzinfo=datetime.timezone.utc)
    # Two predictions, same (ticker, interval) but different horizons —
    # both missing actuals. Should dedupe to ONE refresh call.
    await _insert_prediction(
        ticker="AAPL", interval="1d", made_on=made_on,
        target_ts=target_ts, horizon_offset=1, predicted_close=100.0, task_id="t1",
    )
    await _insert_prediction(
        ticker="AAPL", interval="1d", made_on=made_on,
        target_ts=target_ts + datetime.timedelta(days=1),
        horizon_offset=2, predicted_close=101.0, task_id="t2",
    )

    now = datetime.datetime(2026, 4, 23, tzinfo=datetime.timezone.utc)
    stats = await accuracy_service.evaluate_pending(now=now)

    # Single refresh call despite two pending predictions for the same key.
    assert calls == [("AAPL", "1d")]
    assert stats["ohlcv_refreshed"] == 1
    assert stats["skipped_no_actual"] == 2


@pytest.mark.asyncio
async def test_evaluator_records_miss_after_failed_refresh(client, monkeypatch):
    """A pending target whose bar still doesn't land after refresh should
    create / increment an ``OhlcvFetchMiss`` row."""
    from app.market_data import service as md_service
    from app.accuracy.models import OhlcvFetchMiss

    async def noop_refresh(*_a, **_kw):
        return 0

    monkeypatch.setattr(md_service, "refresh", noop_refresh)

    made_on = datetime.date(2026, 4, 20)
    target_ts = datetime.datetime(2026, 4, 21, 0, 0, 0, tzinfo=datetime.timezone.utc)
    await _insert_prediction(
        ticker="AAPL", interval="1d", made_on=made_on,
        target_ts=target_ts, horizon_offset=1, predicted_close=100.0,
    )

    now = datetime.datetime(2026, 4, 23, tzinfo=datetime.timezone.utc)
    await accuracy_service.evaluate_pending(now=now)

    async with _db.SessionLocal() as s:
        miss = await s.get(OhlcvFetchMiss, ("AAPL", "1d", target_ts))
        assert miss is not None
        assert miss.attempts == 1

    # Second tick → attempts increment.
    await accuracy_service.evaluate_pending(now=now + datetime.timedelta(hours=1))
    async with _db.SessionLocal() as s:
        miss = await s.get(OhlcvFetchMiss, ("AAPL", "1d", target_ts))
        assert miss.attempts == 2


@pytest.mark.asyncio
async def test_evaluator_gives_up_after_max_attempts(client, monkeypatch):
    """Once attempts reach ``MAX_OHLCV_FETCH_ATTEMPTS``, no further refresh
    calls fire for that target — saves the upstream provider from being
    hammered for bars that will never publish."""
    from app.market_data import service as md_service
    from app.accuracy.models import OhlcvFetchMiss

    calls: list[tuple[str, str]] = []

    async def tracking_refresh(symbol, interval, **_kw):
        calls.append((symbol, interval))
        return 0

    monkeypatch.setattr(md_service, "refresh", tracking_refresh)

    made_on = datetime.date(2026, 4, 20)
    target_ts = datetime.datetime(2026, 4, 21, 0, 0, 0, tzinfo=datetime.timezone.utc)
    await _insert_prediction(
        ticker="AAPL", interval="1d", made_on=made_on,
        target_ts=target_ts, horizon_offset=1, predicted_close=100.0,
    )

    # Pre-seed a miss row at the max-attempts threshold.
    async with _db.SessionLocal() as s:
        s.add(OhlcvFetchMiss(
            ticker="AAPL", interval="1d", target_ts=target_ts,
            attempts=accuracy_service.MAX_OHLCV_FETCH_ATTEMPTS,
            last_attempt_at=datetime.datetime(2026, 4, 22, tzinfo=datetime.timezone.utc),
        ))
        await s.commit()

    now = datetime.datetime(2026, 4, 23, tzinfo=datetime.timezone.utc)
    await accuracy_service.evaluate_pending(now=now)

    # No refresh fired despite the missing actual.
    assert calls == []


@pytest.mark.asyncio
async def test_grid_route_accepts_interval_param(client):
    """Route exposes the interval filter and passes it through."""
    r = await client.get("/v1/accuracy/grid?interval=1h", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == []
    assert body["window_size"] == 30
