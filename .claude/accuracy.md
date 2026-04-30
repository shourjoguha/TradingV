# Accuracy + drift detection

Phase 1 of the trust-sprint roadmap. Builds per-(ticker, horizon, model) error metrics over evaluated predictions, surfaces drift, posts to Telegram. See [.claude/roadmap.md](roadmap.md) for the broader plan.

## Schema

`prediction_accuracy` (one row per evaluated prediction):
```
id PK, prediction_id FK→prediction_points (UNIQUE → idempotency, CASCADE),
ticker, model_id, interval, horizon_offset,
made_on DATE, target_date DATE,
predicted_close, actual_close, baseline_close (nullable),
error_pct,            -- signed; (actual - predicted) / actual
abs_error_pct,        -- per-row component of MAPE
squared_error,        -- per-row component of MSE → RMSE
direction_correct,    -- nullable; sign(predicted - baseline) == sign(actual - baseline)
evaluated_at
```

`drift_alerts` (open/ack lifecycle for degraded pairs):
```
id PK, ticker, horizon_offset, model_id,
recent_mape, all_time_mape, ratio,
recent_sample_count, all_time_sample_count,
flagged_at, acknowledged_at (nullable)
```

## Math (per row)

- `error_pct = (actual - predicted) / actual`  (signed; positive = under-prediction)
- `abs_error_pct = |error_pct|`  → aggregated as **MAPE** (mean of abs_error_pct)
- `squared_error = (actual - predicted)²`  → aggregated as **MSE → √ = RMSE**
- `direction_correct = sign(predicted - baseline) == sign(actual - baseline)` with baseline = close at made_on. Edge cases: both flat → `True`, one flat → `False`, baseline missing → `None`.

## Evaluator

`app/accuracy/service.py::evaluate_pending(now=, limit=500)` — finds elapsed predictions (`target_ts <= now`) without an accuracy row, joins to `ohlcv_bars` for actual + baseline, inserts. Idempotent via `UNIQUE(prediction_id)`. Returns `{scanned, evaluated, skipped_no_actual, skipped_bad_data, ohlcv_refreshed}`.

Lifespan loop `evaluator_loop()` ticks hourly. Schedule runner also invokes `evaluate_pending()` synchronously right after `_collect_actuals` (`app/schedule/runner.py`) so the Accuracy tab is fresh by morning instead of up to 1h late. Manual trigger via `POST /v1/accuracy/evaluate`.

### Self-healing OHLCV fetch

When a pending prediction's actual bar is absent from `ohlcv_bars`, the evaluator asks the upstream provider for it. Logic:

- **Per (ticker, interval) per tick:** call `md_service.refresh()` once, then re-query the cache. This dedupes the common case where 40 watchlist tickers × 5 horizons all miss the same day's bar — one refresh, not 200.
- **Per (ticker, interval, target_ts) lifetime cap:** track misses in `ohlcv_fetch_misses`. After `MAX_OHLCV_FETCH_ATTEMPTS = 24` failed attempts (≈ one day at hourly cadence), stop calling the provider for that exact target. Bars that never publish (delisted ticker, holiday, exchange downtime) stop hammering yfinance. The miss row stays as a forensic breadcrumb — you can `SELECT … FROM ohlcv_fetch_misses WHERE attempts >= 24` to see what bars were given up on.

This replaces the old behavior where the evaluator skipped silently and the operator had to manually refresh OHLCV. Both `/accuracy` and `/predictions/by-horizon` now fill in actuals naturally within an hour of the bar being published. See [decisions/010](decisions/010-self-healing-ohlcv-fetch.md).

## Drift detector

`app/accuracy/drift.py::detect_drift(now=, notify=True)` — per (ticker, horizon, model) group:
- Compute `recent_mape` over `evaluated_at >= now - DRIFT_RECENT_WINDOW_DAYS` (30d default).
- Compare to `all_time_mape`.
- Flag if `ratio = recent / all_time >= DRIFT_RATIO_THRESHOLD` (1.5 default) AND both windows meet `DRIFT_MIN_*_SAMPLES` (10 recent, 30 all-time).
- Skip if an open (unacked) `DriftAlert` already exists for the pair → idempotent.
- Post to Telegram on each new flag (no-op if not configured).

Lifespan loop `detector_loop()` ticks every 6 hours. Manual trigger via `POST /v1/accuracy/drift/detect`.

## Endpoints

```
GET   /v1/accuracy/grid?tickers=&horizons=&model_id=&interval=&last_n=30   per-pair MAPE/RMSE/hit-rate
GET   /v1/accuracy/pair?ticker=&horizon_offset=&model_id=                  drilldown rows for one pair
POST  /v1/accuracy/evaluate                                                 manual evaluator tick
GET   /v1/accuracy/drift                                                    open drift alerts
POST  /v1/accuracy/drift/detect                                             manual drift scan
POST  /v1/accuracy/drift/{id}/ack                                           acknowledge → re-flag eligible
```

`interval` is part of the grid grouping key — without filtering, 1h and 1d cadences return as separate rows so they are never averaged together. Each grid row exposes `interval` so the frontend toggle can route correctly.

## Telegram notifier — see [notifications.md](notifications.md)

Drift alerts and the daily digest both use `app/notifications/telegram.py`. The notifier no-ops gracefully when `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` are unset (logged once at startup). Setup steps in [backlog.md](backlog.md) "Unlock #1".

## Files

- `app/accuracy/models.py` — `PredictionAccuracy`, `DriftAlert`, `OhlcvFetchMiss`
- `app/accuracy/service.py` — evaluator + grid/pair queries
- `app/accuracy/drift.py` — drift math + detector loop
- `app/accuracy/routes.py` — 6 endpoints
- `migrations/versions/0012_prediction_accuracy.py`
- `migrations/versions/0013_drift_alerts.py`
- `migrations/versions/0018_ohlcv_fetch_misses.py`
- `tests/test_accuracy.py` — 15 tests covering pure math + evaluator integration + aggregation

## Frontend

`/accuracy` page: ticker × horizon heatmap. Each cell shows two values — directional `hit%` and magnitude `MAPE%` — separated by a slash (e.g. `75% / 4.2%`), with `n=…` underneath. Color is **composite**:

- Green: `hit ≥ 60%` AND `MAPE ≤ 2%`
- Yellow: in-between
- Red: `hit < 50%` OR `MAPE > 4%`
- Grey: `n < 4` (insufficient — no hit/MAPE rendered)

The composite logic exists because hit-rate alone is misleading: a model can be directionally lucky (75% green) while every magnitude is materially off. Surfacing MAPE next to it kills that false-green case.

**Interval toggle (`1d | 1h | all`)** above the table filters rows by interval so 1h-cadence runs are never averaged into 1d statistics.

**Hover tooltip** (no click needed): hovering or focusing a cell opens an inline drilldown panel below the matrix with per-prediction error rows. Click also pins the panel; the close button dismisses it. Drift-alert banner at top with one-click ack. Manual "Evaluate" button. Window-size selector (10/30/100/500).

Thresholds and `MIN_N` live as constants at the top of `frontend/src/pages/Accuracy.tsx` for easy tuning.
