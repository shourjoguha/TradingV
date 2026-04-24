# Alerts module (`app/alerts/`)

TradingView webhook ingestion. Oldest module — preserved from original repo.

## Endpoints (unversioned, legacy — do not break)
- `POST /webhook` — auth via `X-API-Key`. Body `{ticker, alert_type, payload_json}`. Returns `{"status":"ok"}` immediately; DB write is a `BackgroundTask`.
- `GET /alerts` — auth. Returns rows where `is_read = False`, then flips them to `True` (**destructive read — intentional, see below**).

## Schema — `alerts` table
`id, ticker VARCHAR(50), timestamp, alert_type VARCHAR(50), payload_json JSON, is_read BOOL`.

## Destructive read — decision record
Kept as-is. Ticker registry derives from ALL alerts regardless of `is_read`, so destructive read does not harm the registry. Revisit only if a second consumer needs `/alerts`.

## Cross-module side effect
`save_alert` also upserts the ticker into `tickers` (source=`alert`) in the same transaction. This is the only cross-module write in the codebase today. If you add more, document them here.

## Known gaps
- No validation on `payload_json` shape — TradingView alert format is freeform.
- No ticker normalization at ingest (registry upsert normalizes to uppercase, but `alerts.ticker` preserves original casing). Flag if this becomes a query problem.
