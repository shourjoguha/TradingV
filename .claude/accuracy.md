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

`app/accuracy/service.py::evaluate_pending(now=, limit=500)` — finds elapsed predictions (`target_ts <= now`) without an accuracy row, joins to `ohlcv_bars` for actual + baseline, inserts. Idempotent via `UNIQUE(prediction_id)`. Returns `{scanned, evaluated, skipped_no_actual, skipped_bad_data}`.

Lifespan loop `evaluator_loop()` ticks hourly. Manual trigger via `POST /v1/accuracy/evaluate`.

**Known gap**: when an actual is missing from `ohlcv_bars` the evaluator skips silently — see [backlog.md](backlog.md) "Unlock #2" for the on-demand-refresh fix.

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
GET   /v1/accuracy/grid?tickers=&horizons=&model_id=&last_n=30   per-pair MAPE/RMSE/hit-rate over rolling window
GET   /v1/accuracy/pair?ticker=&horizon_offset=&model_id=        drilldown rows for one pair
POST  /v1/accuracy/evaluate                                       manual evaluator tick
GET   /v1/accuracy/drift                                          open drift alerts
POST  /v1/accuracy/drift/detect                                   manual drift scan
POST  /v1/accuracy/drift/{id}/ack                                 acknowledge → re-flag eligible
```

## Telegram notifier — see [notifications.md](notifications.md)

Drift alerts and the daily digest both use `app/notifications/telegram.py`. The notifier no-ops gracefully when `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` are unset (logged once at startup). Setup steps in [backlog.md](backlog.md) "Unlock #1".

## Files

- `app/accuracy/models.py` — `PredictionAccuracy`, `DriftAlert`
- `app/accuracy/service.py` — evaluator + grid/pair queries
- `app/accuracy/drift.py` — drift math + detector loop
- `app/accuracy/routes.py` — 6 endpoints
- `migrations/versions/0012_prediction_accuracy.py`
- `migrations/versions/0013_drift_alerts.py`
- `tests/test_accuracy.py` — 15 tests covering pure math + evaluator integration + aggregation

## Frontend

`/accuracy` page: ticker × horizon heatmap colored by hit-rate (green ≥60%, yellow ≥50%, red <50%); cell hover shows MAPE/RMSE/n; cell click opens drilldown modal with per-prediction error rows. Drift-alert banner at top with one-click ack. Manual "Evaluate" button. Window-size selector (10/30/100/500).
