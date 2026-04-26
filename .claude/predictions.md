# Predictions

Flat materialised view of `analysis_tasks.result_json.forecast[]` — one row per (task, target bar). Powers the comparison endpoints in Phase 5.

## Schema
```
prediction_points(
  id PK, task_id FK→analysis_tasks (CASCADE),
  ticker, model_id, interval,
  made_on DATE, made_on_dow SMALLINT,        -- Mon=0..Sun=6
  target_date DATE, target_ts TIMESTAMPTZ,
  horizon_offset SMALLINT,                    -- 1, 2, 3, ...
  open, high, low, close, volume?, amount?,
  created_at
)
```

## Indexes
- `(target_date, ticker)` — "what did we predict for target X?"
- `(made_on, ticker)` — "all forecasts made on day Y"
- `(ticker, target_date, made_on)` — "predictions made k-days-ago vs actual"
- `(made_on_dow)` — "Friday-only forecasts"

## Auto-population
- **Live**: `_process_task` calls `predictions.service.explode_task(task_id)` after the task transitions to `done` (best-effort; failure logged, doesn't roll back the task commit).
- **Imported**: `import_job` calls `predictions.service.explode_imported_tasks(payload)` after inserting the imported job + tasks.

Idempotent: each call clears any existing rows for the task before inserting fresh.

## Backfill
`POST /v1/predictions/backfill` — re-derives rows from every `analysis_tasks` where `status='done'` and `result_json` non-empty.

Query params:
- `since=YYYY-MM-DD` — only tasks with `started_at >= since`
- `only_missing=true` (default) — skip tasks that already have rows. Set false to fully rewrite (e.g. after a forecast-format change).

Returns `{scanned, exploded, rows_inserted, skipped}`.

## Comparison endpoints (Phase 5)

### `GET /v1/predictions/by-target`
Drill-down for one (ticker, target_date). Returns the actual bar (or null) plus every prediction ever made for that target, sorted made_on DESC.

Query params:
- `ticker` (required)
- `target_date` (required, YYYY-MM-DD)
- `interval` (default `1d`)
- `model_id` (optional filter)
- `fields` — preset (`o|h|l|c|v|a|ohlc|ohlcv|all`) OR CSV (`close,high`). Default `ohlcv`.
- `made_on_dow` — CSV of weekday ints (Mon=0..Sun=6). Filters to predictions made on those weekdays.

Response:
```
{
  ticker, target_date, interval, fields: [...],
  actual: {open, high, low, close, ...} | null,
  predictions: [
    {made_on, made_on_dow, days_ago, horizon_offset, model_id, interval, ...fields},
    ...
  ]
}
```

### `GET /v1/predictions/by-horizon`
Multi-ticker grid: for one `target_date`, return predictions made N calendar days before across N tickers. Missing cells yield `prediction: null` (not omitted).

Query params:
- `target_date` (required)
- `horizons` — CSV positive ints, e.g. `1,2,3,4,5`
- `tickers` — CSV, e.g. `AAPL,MSFT,NVDA`
- `interval`, `model_id`, `fields`, `made_on_dow` — same as above

Response: `{target_date, interval, fields, rows: [{ticker, target_date, made_on, days_ago, actual, prediction}, ...]}`. Length = `len(tickers) × len(horizons)`.

### Field selector grammar
- Presets: `o|h|l|c|v|a|ohlc|ohlcv|all`
- CSV: any subset of `open,high,low,close,volume,amount`
- Unknown fields silently dropped. Empty result falls back to default (`ohlcv`).

## Source-of-truth note
`analysis_tasks.result_json` is canonical. `prediction_points` is a queryable cache. Backfill regenerates it on demand. If the format ever changes, set `only_missing=false` and re-run.
