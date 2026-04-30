"""Accuracy evaluator + aggregations.

Two write paths:
- :func:`evaluate_pending` — finds elapsed predictions without an accuracy row,
  joins to ``ohlcv_bars`` for actual + baseline, inserts. Idempotent via the
  ``UNIQUE(prediction_id)`` constraint. Called from a lifespan loop hourly.
- :func:`evaluator_loop` — long-lived task wrapping :func:`evaluate_pending`.

Two read paths used by routes + dashboard:
- :func:`accuracy_grid` — heatmap rows: per (ticker, horizon) → MAPE, RMSE,
  hit-rate over a rolling window. Powers the ``/accuracy`` page.
- :func:`pair_history` — drilldown: raw rows for one (ticker, horizon, model)
  pair. Powers the cell-click scatter view.

Math:
- ``error_pct = (actual - predicted) / actual``  (signed; positive = under-prediction)
- ``abs_error_pct = abs(error_pct)``             (per-row component of MAPE)
- ``squared_error = (actual - predicted)^2``     (per-row component of MSE → RMSE)
- ``direction_correct = sign(predicted - baseline) == sign(actual - baseline)``
  with baseline = close at made_on (T0). Null if baseline missing.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Iterable, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accuracy.models import OhlcvFetchMiss, PredictionAccuracy
from app.core import db as _db
from app.market_data import service as md_service
from app.market_data.models import OhlcvBar
from app.predictions.models import PredictionPoint
from app.tickers import service as tickers_svc

logger = logging.getLogger(__name__)

# How often the lifespan loop ticks. Hourly is plenty — actuals only land
# after each bar closes, and the evaluator is cheap when nothing's pending.
_DEFAULT_TICK_SECONDS = 60 * 60

# Cap how many times we ask the provider for the same (ticker, interval,
# target_ts) bar. Hourly tick × 24 = give up after one day of trying. Beyond
# that the bar likely never existed (delisted ticker, holiday, exchange
# closure) and retrying just hammers the upstream provider.
MAX_OHLCV_FETCH_ATTEMPTS = 24


def _safe_div(num: float, den: float) -> float | None:
    if den == 0:
        return None
    return num / den


def _compute_metrics(
    *,
    predicted_close: float,
    actual_close: float,
    baseline_close: Optional[float],
) -> dict[str, Any]:
    """Per-row error metrics. Returns dict ready for PredictionAccuracy kwargs.

    Skips the row entirely (returns None) when ``actual_close`` is 0 or
    negative — division-by-zero or non-physical price.
    """
    if actual_close <= 0:
        return {}

    diff = actual_close - predicted_close
    err_pct = diff / actual_close
    abs_err_pct = abs(err_pct)
    squared = diff * diff

    direction_correct: Optional[bool] = None
    if baseline_close is not None and baseline_close > 0:
        pred_dir = predicted_close - baseline_close
        actual_dir = actual_close - baseline_close
        # Both flat = trivially correct (no movement either way).
        if pred_dir == 0 and actual_dir == 0:
            direction_correct = True
        elif pred_dir == 0 or actual_dir == 0:
            # One predicts movement, the other doesn't → wrong call.
            direction_correct = False
        else:
            direction_correct = (pred_dir > 0) == (actual_dir > 0)

    return {
        "predicted_close": float(predicted_close),
        "actual_close": float(actual_close),
        "baseline_close": float(baseline_close) if baseline_close is not None else None,
        "error_pct": float(err_pct),
        "abs_error_pct": float(abs_err_pct),
        "squared_error": float(squared),
        "direction_correct": direction_correct,
    }


async def _fetch_actual_close(
    session: AsyncSession,
    *,
    ticker: str,
    interval: str,
    target_ts: datetime.datetime,
) -> Optional[float]:
    """Look up the actual close at the prediction's exact target timestamp.

    Returns None when the bar isn't in cache (target hasn't elapsed yet, or
    OHLCV refresh hasn't run for this period). The evaluator skips silently
    in that case and retries on the next tick.
    """
    stmt = select(OhlcvBar.close).where(
        OhlcvBar.symbol == ticker,
        OhlcvBar.interval == interval,
        OhlcvBar.ts == target_ts,
    )
    return await session.scalar(stmt)


async def _fetch_baseline_close(
    session: AsyncSession,
    *,
    ticker: str,
    interval: str,
    made_on: datetime.date,
) -> Optional[float]:
    """Find the close on ``made_on`` (T0) for direction correctness.

    Picks the latest bar on the made_on calendar date — handles intraday
    intervals where multiple bars exist per day. None if no bar found.
    """
    start = datetime.datetime.combine(made_on, datetime.time.min, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(days=1)
    stmt = (
        select(OhlcvBar.close)
        .where(
            OhlcvBar.symbol == ticker,
            OhlcvBar.interval == interval,
            OhlcvBar.ts >= start,
            OhlcvBar.ts < end,
        )
        .order_by(OhlcvBar.ts.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


async def _try_refresh_actual(
    session: AsyncSession,
    *,
    pp: PredictionPoint,
    refreshed_keys: set[tuple[str, str]],
    now: datetime.datetime,
    stats: dict[str, int],
) -> Optional[float]:
    """Try to make the bar for ``pp.target_ts`` exist by asking the upstream
    provider. Returns the new actual close, or None if still missing.

    Side effects:
    - Calls ``md_service.refresh(ticker, interval)`` at most once per tick
      per ``(ticker, interval)`` (dedupe via ``refreshed_keys``).
    - Increments / inserts an ``OhlcvFetchMiss`` row when the refresh
      doesn't surface the bar.
    - Skips the refresh entirely once attempts >= ``MAX_OHLCV_FETCH_ATTEMPTS``
      for this exact ``(ticker, interval, target_ts)`` triple.
    """
    miss = await session.get(
        OhlcvFetchMiss, (pp.ticker, pp.interval, pp.target_ts)
    )
    if miss is not None and miss.attempts >= MAX_OHLCV_FETCH_ATTEMPTS:
        # Already gave up. Cache might still be populated by another path
        # (manual refresh, schedule runner), so we don't actively skip the
        # cache re-check; we just don't trigger another provider call.
        return None

    key = (pp.ticker, pp.interval)
    if key not in refreshed_keys:
        refreshed_keys.add(key)
        # Resolve asset_class for refresh; refresh accepts None and falls
        # back to ticker registry, so even a brand-new symbol works.
        try:
            await md_service.refresh(pp.ticker, pp.interval)
            stats["ohlcv_refreshed"] += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "accuracy.evaluator: ohlcv refresh failed for %s/%s: %s",
                pp.ticker,
                pp.interval,
                e,
            )

    actual = await _fetch_actual_close(
        session,
        ticker=pp.ticker,
        interval=pp.interval,
        target_ts=pp.target_ts,
    )
    if actual is not None:
        return float(actual)

    # Still missing — record / increment the miss.
    if miss is None:
        session.add(
            OhlcvFetchMiss(
                ticker=pp.ticker,
                interval=pp.interval,
                target_ts=pp.target_ts,
                attempts=1,
                last_attempt_at=now,
            )
        )
    else:
        miss.attempts += 1
        miss.last_attempt_at = now
    return None


async def evaluate_pending(
    *,
    now: Optional[datetime.datetime] = None,
    limit: int = 500,
) -> dict[str, int]:
    """Insert ``PredictionAccuracy`` rows for elapsed predictions missing one.

    A prediction is eligible when:
    - ``target_ts <= now`` (the bar has elapsed; actual is in principle knowable)
    - No ``PredictionAccuracy`` row exists for this ``prediction_id``
    - The actual close exists in ``ohlcv_bars`` for the exact target timestamp

    Returns ``{"scanned", "evaluated", "skipped_no_actual", "skipped_bad_data",
    "ohlcv_refreshed"}``.

    When the bar for a pending prediction's ``target_ts`` is absent from
    ``ohlcv_bars``, this function attempts a provider refresh once per
    ``(ticker, interval)`` per tick (deduped within the loop), then re-checks
    the cache. A ``OhlcvFetchMiss`` row tracks per-target attempt counts so we
    stop hammering yfinance after ``MAX_OHLCV_FETCH_ATTEMPTS`` for a target
    that simply never publishes.

    Safe to call concurrently — the UNIQUE(prediction_id) constraint is the
    final gate; conflicts are caught and counted under ``skipped_bad_data``.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stats = {
        "scanned": 0,
        "evaluated": 0,
        "skipped_no_actual": 0,
        "skipped_bad_data": 0,
        "ohlcv_refreshed": 0,
    }

    async with _db.SessionLocal() as session:
        existing_subq = select(PredictionAccuracy.prediction_id).scalar_subquery()
        stmt = (
            select(PredictionPoint)
            .where(
                PredictionPoint.target_ts <= now,
                PredictionPoint.id.notin_(existing_subq),
            )
            .order_by(PredictionPoint.target_ts.asc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).scalars().all()
        stats["scanned"] = len(rows)

        # Per-tick dedupe so a watchlist of 40 symbols × 5 horizons all
        # missing the same day's bars triggers one refresh per (ticker,
        # interval), not 200.
        refreshed_keys: set[tuple[str, str]] = set()

        for pp in rows:
            actual = await _fetch_actual_close(
                session,
                ticker=pp.ticker,
                interval=pp.interval,
                target_ts=pp.target_ts,
            )
            if actual is None:
                # Try to make the bar exist. Per (ticker, interval) once per
                # tick; per (ticker, interval, target_ts) capped at
                # MAX_OHLCV_FETCH_ATTEMPTS lifetime so unfetchable targets
                # don't hammer yfinance forever.
                actual = await _try_refresh_actual(
                    session,
                    pp=pp,
                    refreshed_keys=refreshed_keys,
                    now=now,
                    stats=stats,
                )
            if actual is None:
                stats["skipped_no_actual"] += 1
                continue

            baseline = await _fetch_baseline_close(
                session, ticker=pp.ticker, interval=pp.interval, made_on=pp.made_on
            )

            metrics = _compute_metrics(
                predicted_close=pp.close,
                actual_close=float(actual),
                baseline_close=float(baseline) if baseline is not None else None,
            )
            if not metrics:
                stats["skipped_bad_data"] += 1
                continue

            row = PredictionAccuracy(
                prediction_id=pp.id,
                ticker=pp.ticker,
                model_id=pp.model_id,
                interval=pp.interval,
                horizon_offset=pp.horizon_offset,
                made_on=pp.made_on,
                target_date=pp.target_date,
                **metrics,
            )
            session.add(row)
            try:
                await session.flush()
                stats["evaluated"] += 1
            except IntegrityError:
                # Another worker beat us to it — UNIQUE(prediction_id) fired.
                # Roll back this insert and keep going. Counts as not-our-write.
                await session.rollback()
                stats["skipped_bad_data"] += 1

        await session.commit()
    return stats


async def evaluator_loop(
    *, tick_seconds: int = _DEFAULT_TICK_SECONDS, stop_event: Optional[asyncio.Event] = None
) -> None:
    """Long-lived lifespan task. Calls :func:`evaluate_pending` every tick.

    Cancellation-safe: catches CancelledError on its own waits and exits
    cleanly. Errors during evaluation are logged and the loop continues —
    one bad tick shouldn't kill the loop.
    """
    logger.info("accuracy.evaluator_loop started (tick=%ss)", tick_seconds)
    while True:
        try:
            stats = await evaluate_pending()
            if stats["evaluated"] > 0:
                logger.info(
                    "accuracy.evaluator: scanned=%d evaluated=%d skipped_no_actual=%d skipped_bad_data=%d",
                    stats["scanned"],
                    stats["evaluated"],
                    stats["skipped_no_actual"],
                    stats["skipped_bad_data"],
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("accuracy.evaluator tick failed: %s", e)

        try:
            if stop_event is not None:
                # Wait either for the next tick or for the shutdown signal.
                await asyncio.wait_for(stop_event.wait(), timeout=tick_seconds)
                if stop_event.is_set():
                    logger.info("accuracy.evaluator_loop stopping (signal)")
                    return
            else:
                await asyncio.sleep(tick_seconds)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise


# ----------------------------------------------------------------------
# Read aggregations (powering /accuracy dashboard)
# ----------------------------------------------------------------------


async def accuracy_grid(
    *,
    tickers: Optional[Iterable[str]] = None,
    horizons: Optional[Iterable[int]] = None,
    model_id: Optional[str] = None,
    interval: Optional[str] = None,
    last_n: int = 30,
    since: Optional[datetime.date] = None,
) -> list[dict[str, Any]]:
    """Per-(ticker, horizon) accuracy summary.

    For each grouping returns the most recent ``last_n`` evaluations and
    aggregates them into MAPE, RMSE, directional hit-rate, and a sample
    count. Filters: optional ticker subset, optional horizon subset,
    optional model_id, optional ``since`` cutoff on ``evaluated_at``.

    Returns a list of dicts with keys::

        ticker, horizon_offset, model_id,
        sample_count, mape, rmse, hit_rate, latest_eval
    """
    out: list[dict[str, Any]] = []
    async with _db.SessionLocal() as session:
        # Discover the (ticker, horizon, model, interval) groups that have any
        # data. Interval is part of the grouping key — 1h and 1d cadences must
        # not be averaged together.
        groups_stmt = select(
            PredictionAccuracy.ticker,
            PredictionAccuracy.horizon_offset,
            PredictionAccuracy.model_id,
            PredictionAccuracy.interval,
        ).distinct()
        if tickers:
            groups_stmt = groups_stmt.where(PredictionAccuracy.ticker.in_(list(tickers)))
        if horizons:
            groups_stmt = groups_stmt.where(
                PredictionAccuracy.horizon_offset.in_(list(horizons))
            )
        if model_id:
            groups_stmt = groups_stmt.where(PredictionAccuracy.model_id == model_id)
        if interval:
            groups_stmt = groups_stmt.where(PredictionAccuracy.interval == interval)
        groups = (await session.execute(groups_stmt)).all()

        for ticker, horizon, mid, ivl in groups:
            row_stmt = (
                select(
                    PredictionAccuracy.abs_error_pct,
                    PredictionAccuracy.squared_error,
                    PredictionAccuracy.direction_correct,
                    PredictionAccuracy.evaluated_at,
                )
                .where(
                    PredictionAccuracy.ticker == ticker,
                    PredictionAccuracy.horizon_offset == horizon,
                    PredictionAccuracy.model_id == mid,
                    PredictionAccuracy.interval == ivl,
                )
                .order_by(PredictionAccuracy.evaluated_at.desc())
                .limit(last_n)
            )
            if since is not None:
                row_stmt = row_stmt.where(PredictionAccuracy.evaluated_at >= since)

            rows = (await session.execute(row_stmt)).all()
            if not rows:
                continue

            n = len(rows)
            mape = sum(r.abs_error_pct for r in rows) / n
            mse = sum(r.squared_error for r in rows) / n
            rmse = mse ** 0.5
            with_dir = [r for r in rows if r.direction_correct is not None]
            hit_rate = (
                sum(1 for r in with_dir if r.direction_correct) / len(with_dir)
                if with_dir
                else None
            )
            latest = max(r.evaluated_at for r in rows)

            out.append(
                {
                    "ticker": ticker,
                    "horizon_offset": horizon,
                    "model_id": mid,
                    "interval": ivl,
                    "sample_count": n,
                    "mape": mape,
                    "rmse": rmse,
                    "hit_rate": hit_rate,
                    "latest_eval": latest.isoformat() if latest else None,
                }
            )

    return out


async def pair_history(
    *,
    ticker: str,
    horizon_offset: int,
    model_id: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Drilldown: per-prediction rows for one (ticker, horizon, model) pair."""
    async with _db.SessionLocal() as session:
        stmt = (
            select(PredictionAccuracy)
            .where(
                PredictionAccuracy.ticker == ticker,
                PredictionAccuracy.horizon_offset == horizon_offset,
            )
            .order_by(PredictionAccuracy.evaluated_at.desc())
            .limit(limit)
        )
        if model_id:
            stmt = stmt.where(PredictionAccuracy.model_id == model_id)

        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "prediction_id": r.prediction_id,
                "model_id": r.model_id,
                "made_on": r.made_on.isoformat(),
                "target_date": r.target_date.isoformat(),
                "predicted_close": r.predicted_close,
                "actual_close": r.actual_close,
                "baseline_close": r.baseline_close,
                "error_pct": r.error_pct,
                "abs_error_pct": r.abs_error_pct,
                "squared_error": r.squared_error,
                "direction_correct": r.direction_correct,
                "evaluated_at": r.evaluated_at.isoformat(),
            }
            for r in rows
        ]
