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
- **macro_series** — Daily close-only macro time-series (yfinance + FRED). UNIQUE `(symbol, ts)`. Powers the Macro Workbench `/v1/macro/*` endpoints. Daily-only by design; not OHLCV. Separate from `ohlcv_bars` — see [decisions/012](../decisions/012-macro-workbench-storage-shape.md).
- **ohlcv_fetch_misses** — Per `(ticker, interval, target_ts)` give-up counter for the self-healing OHLCV fetch in the accuracy evaluator. See [decisions/010](../decisions/010-self-healing-ohlcv-fetch.md).

## Macro Workbench

- **regime** — A multi-month/multi-quarter market state that biases ratios and asset returns systematically (e.g. risk-on, debasement, recession). The workbench's job is to surface which regime the data is currently in.
- **ratio (macro)** — `numerator/denominator` of two `macro_series` symbols, computed at query time. Twelve+ canonical ratios cover the v1 spec (e.g. `GC=F/SPY`, `RSP/SPY`, `HYG/LQD`).
- **yield curve panel** (added 2026-05-17) — 6th regime panel surfacing US Treasury curve shape + recession-signal spreads. Rows: `WGS2YR` (2Y), `WGS10YR` (10Y), `WGS30YR` (30Y — operator-tracked "all-important 5%" level), `T10Y2Y` (2s10s spread), `T10Y3M` (NY Fed model input). Sourced from vault-audit of `Videos/{click-capital, fx-evolution-daily}` where curve shape is repeatedly flagged. See `.claude/decisions/macro-yields-rework-2026-05-17/`.
- **MOVE index** — ICE BofA bond-market volatility index (`^MOVE` on yfinance). Bond-market equivalent of VIX. Surfaced beside VIX in the Stress panel since 2026-05-17. Below 80 = calm; 80-120 normal; >180 crisis. Operator-flagged as leading indicator (fx-evolution-daily-w19).
- **hypothesis** — Operator-authored thesis about a regime/asset move, with TTL, invalidators, and confirming/violating status. Markdown drafts under `.claude/hypotheses/draft/` until M-2 ships the DB-backed object.
- **claim_type** — `absolute` | `relative` | `absolute_with_relative_signal`. The third covers the common pattern where the bet is on absolute returns but the early-warning signal is a relative ratio.
- **precondition (hypothesis)** — Existence dependency: if precondition `violated`, dependent auto-cancels. Different from `parent_id` (sizing dependency, no cascade).

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

## TV Context + decision-engine enrichment (2026-05-17)

- **tv_context_items** — Polymorphic table holding webhook / note / idea / event / screenshot inputs. Per-kind retention. Decay-weighted into rec attention scores; linked to hypotheses for invalidator triggers.
- **HypothesisTVContextLink** — Pointer table (hypothesis_id × tv_context_item_id) with `stance` column (`supports` / `challenges` / `context`). Operator-stamped at screenshot ingest time.
- **ticker_review_queue** — Unknown-ticker review surface. Fed by Stage 1 video-vision AND TV-context ingest (Phase 1 parity, shipped 2026-05-17). Resolve via Today strip → adds to roster / board.
- **attention_score** — Float on `recommendations`. Σ across all tickers in rec text of `kind_weight × exp(-ln2 × age_d / 7)` for TV-context items in trailing 14d. MAX across tickers, not sum. Stamped at rec creation; null on legacy rows.
- **attention_breakdown** — JSON on `recommendations`. `{ticker: {kind: count, score: float}}`. Powers the violet 👁️ "Operator attention" badge on `/motion/recs/:id`.
- **tv_context_count_since** — Invalidator DSL op. `args: {days, min_count}`. Fires when ≥ min_count `HypothesisTVContextLink` rows exist in trailing window.
- **tv_context_stance_count_since** — Stance-filtered version. `args: {days, stance, min_count}`. Operator-facing "evidence against" = `stance="challenges"`.

## Backends + deployment

- **laptop / Railway** — The two deployment targets. Bidirectional sync via Tailscale.
- **CF Pages** — Cloudflare Pages, the frontend host. Bundle at `tradingv-83b.pages.dev`.
- **operator** — The single human user.
