# Glossary

Terms used across docs and code. One line each.

## Time + horizons

- **horizon** — Number of bars into the future a prediction looks. Stored as `horizon_offset` on `prediction_points`.
- **horizon_offset** — Integer >= 1; "1 = first bar after made_on, 2 = second, etc." For 1d interval, horizon_offset=5 means "5 trading days out."
- **made_on** — UTC date when the forecast was generated (≈ `task.started_at.date()`).
- **made_on_dow** — Python weekday: Mon=0..Sun=6. Indexed for `?made_on_dow=` filter.
- **target_date** — UTC date the predicted bar covers.
- **target_ts** — UTC timestamp of the predicted bar (granular for intraday).
- **days_ago** — `(target_date - made_on).days`. Used in by-horizon comparison.

## Accuracy + drift

- **MAPE** — Mean Absolute Percentage Error. Aggregated from per-row `abs_error_pct`.
- **RMSE** — Root Mean Squared Error. `sqrt(mean(squared_error))`.
- **hit-rate** — Directional accuracy: fraction of predictions whose sign matched the actual move from baseline.
- **baseline_close** — Close at `made_on` (T0). The "starting price" for direction comparison.
- **direction_correct** — `sign(predicted - baseline) == sign(actual - baseline)`. Null when baseline missing.
- **drift ratio** — `recent_30d_mape / all_time_mape`. Triggers a drift alert when > `DRIFT_RATIO_THRESHOLD` (default 1.5).
- **drift alert** — Open/ack lifecycle row in `drift_alerts` flagging a (ticker, horizon, model) pair whose recent accuracy degraded.

## Tables

- **prediction_points** — Flat materialised view of `analysis_tasks.result_json.forecast[]`. One row per (task, target bar).
- **prediction_accuracy** — One row per evaluated prediction. UNIQUE(prediction_id) for idempotency.
- **drift_alerts** — Open/ack flags from the drift detector.
- **opportunities** — Rule-fired signals. UNIQUE(source_prediction_id, rule_id) for idempotency.
- **trades** — Manual trade journal. Optional FK to `opportunities` for per-rule P&L attribution.
- **submit_queue** — Tier-1 job submission queue. Worker drains FIFO.
- **ticker_market_data** — Phase 6 derived metrics (IV percentile, earnings dates).
- **ohlcv_bars** — OHLCV cache. Composite PK `(symbol, interval, ts)`.

## Opportunities

- **opportunity** — A signal that crossed a threshold rule. Lifecycle: pending → acted | dismissed | expired.
- **rule R1 / R2 / R3** — Hardcoded buy/sell thresholds in `app/opportunities/rules.py`. R1: BUY +2%/5d; R2: SELL -2%/5d; R3: BUY +5%/10d. All require historical hit-rate.
- **confidence** — Snapshot of historical hit-rate at signal generation. Doesn't update.
- **predicted_move_pct** — Signed; `(predicted_close - baseline) / baseline`.

## Queue

- **queue source (manual/schedule/fallback)** — Provenance of a `submit_queue` row.
- **claim_next** — Worker's atomic "grab the oldest pending" call. Uses `FOR UPDATE SKIP LOCKED` on Postgres.
- **request_wake** — Public hook to interrupt the worker's poll sleep when a new item lands.
- **reset_stuck_on_boot** — Lifespan recovery: flips any `running` row to `pending` so the worker re-picks it.

## Sync

- **outbox** — `sync_outbox` table. Holds rows pending push to peer (kind: `ticker` | `result` | `watchlist` | `schedule` | `label`).
- **drain** — `sync_service.drain_outbox()` — best-effort push to peer + mark complete or back off.
- **origin** — `analysis_jobs.origin` column. `'self'` (local-created) or `'peer'` (imported from peer's outbox push).

## Frontend / design system

- **Neumorphism** — Light-only design system; monochromatic cool grey (`#E0E5EC`) with dual opposing RGBA shadows for extruded/inset depth.
- **inset / extruded** — Shadow direction. Inset = pressed in, extruded = raised out.
- **neumorphic-toned** — Semantic colors (success/danger/warning) muted to match the cool grey palette.
- **compact-neumorphic** — Density variant: neumorphic shadows + radii + palette, but data tables stay tight (`p-3`–`p-6`).

## Schedule

- **fallback_offset_hours** — How long after the daily run-time Railway waits before firing its own (when `RAILWAY_FALLBACK_ENABLED=true`).
- **deferred_429** — Historical schedule status; unreachable under the queue (kept in DB for back-compat).

## Backends + deployment

- **laptop / Railway** — The two deployment targets. Bidirectional sync via Tailscale.
- **CF Pages** — Cloudflare Pages, the frontend host. Bundle at `tradingv-83b.pages.dev`.
- **operator** — The single human user.
