# Migrations (Alembic)

Schema is owned by Alembic. `migrations/versions/NNNN_*.py` is the source of truth.

## Commands
- Apply: `alembic upgrade head`
- New rev: `alembic revision -m "message"` (hand-edit — autogenerate not wired yet)
- Downgrade one: `alembic downgrade -1`

## Driver note
Alembic uses **sync** psycopg2 (not asyncpg). `migrations/env.py` rewrites `postgresql+asyncpg://` → `postgresql+psycopg2://` automatically. Both drivers are in `requirements.txt` on purpose.

## Deploy wiring
`Procfile` has `release: alembic upgrade head`. `railway.toml` has the same in `startCommand` as a fallback (Railway release commands are optional depending on service config; belt-and-suspenders).

## Idempotency
All migrations guard with `inspect(bind).get_table_names()` before `create_table` so they're safe to run against a DB that was first initialized via `Base.metadata.create_all` (legacy path). Do not remove these guards until you've confirmed every deployed env has run migrations at least once.

## Current revisions
- `0001` — baseline `alerts` table (matches original repo schema)
- `0002` — `tickers` table + data backfill from `SELECT DISTINCT ticker FROM alerts`
- `0003` — `ohlcv_bars` cache table + `(symbol, interval, ts DESC)` index
- `0004` — `analysis_jobs` + `analysis_tasks` (UUID pk, FK cascade on delete)

## Backfills
When adding backfill logic to a migration, dialect-branch (`bind.dialect.name`) for portability: `ON CONFLICT` (Postgres) vs `INSERT OR IGNORE` (SQLite, used in tests).
