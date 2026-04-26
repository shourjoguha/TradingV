# Migrations (Alembic)

Schema is owned by Alembic. `migrations/versions/NNNN_*.py` is the source of truth.

## Commands
- Apply: `alembic upgrade head`
- New rev: `alembic revision -m "message"` (hand-edit — autogenerate not wired yet)
- Downgrade one: `alembic downgrade -1`

## Driver note
Alembic uses **sync** psycopg2 (not asyncpg). `migrations/env.py` rewrites `postgresql+asyncpg://` → `postgresql+psycopg2://` automatically. Both drivers are in `requirements.txt` on purpose.

## Deploy wiring
`railway.toml` has `startCommand = "alembic upgrade head && uvicorn ..."` so migrations run at container start, before the web process binds the port. `Procfile` is just `web: uvicorn ...` — no `release:` phase, because Railpack runs that at BUILD time when the DB isn't yet available. See [railway-deployment.md](railway-deployment.md) for the full Railpack-vs-Nixpacks notes.

## Idempotency
All migrations guard with `inspect(bind).get_column_names()` / `get_table_names()` before mutating, so they're safe to run against a DB that was first initialised via `Base.metadata.create_all` (legacy path) and re-runs are no-ops. Some migrations also dialect-branch (e.g. SQLite can't `ALTER COLUMN` to relax NOT NULL — skip on SQLite, apply on Postgres).

## Current revisions
- `0001` — baseline `alerts` table (matches original repo schema)
- `0002` — `tickers` table + data backfill from `SELECT DISTINCT ticker FROM alerts`
- `0003` — `ohlcv_bars` cache table + `(symbol, interval, ts DESC)` index
- `0004` — `analysis_jobs` + `analysis_tasks` (UUID pk, FK cascade on delete)
- `0005` — `sync_outbox` table + `ix_sync_outbox_pending` index
- `0006` — replication extensions: `sync_outbox.kind` + `sync_outbox.payload_json`, `analysis_jobs.origin`. Relaxes `sync_outbox.symbol` / `asset_class` to NULLABLE on Postgres (kind='result' rows omit them).
- `0007` — `watchlist` table (symbol PK FK→tickers CASCADE)
- `0008` — `schedule_config` singleton table + seed row id=1 with locked defaults
- `0009` — `prediction_points` flat table + 4 indexes for comparison queries
- `0010` — `ticker_labels` EAV table + `(symbol, key)` UNIQUE + `(key)` index

## Backfills
When adding backfill logic to a migration, dialect-branch (`bind.dialect.name`) for portability: `ON CONFLICT` (Postgres) vs `INSERT OR IGNORE` (SQLite, used in tests).

For application-level backfills (e.g. `prediction_points` from existing `analysis_tasks.result_json`), prefer a route handler (`POST /v1/predictions/backfill`) over an Alembic data migration — keeps schema migrations small + lets ops re-run with different filters.
