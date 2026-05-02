# Testing

`pytest` + `pytest-asyncio` (auto mode) + `httpx.AsyncClient` against ASGI transport. DB = SQLite in-memory per test via `aiosqlite`.

## Running
```
source venv/bin/activate
python -m pytest
```

## Fixture pattern (`tests/conftest.py`)
The `client` fixture monkey-patches `app.core.db.engine` and `app.core.db.SessionLocal` to a fresh in-memory SQLite engine, creates all tables via `Base.metadata.create_all`, then imports `app.main:app` and returns an `AsyncClient`. Each test gets a fully isolated DB.

## Background tasks

`tests/conftest.py` sets `DISABLE_LIFESPAN_BACKGROUND_TASKS=1` at module top, before any app import. The `app/main.py` lifespan checks the flag and `yield`s **without spawning** any of: queue worker, accuracy evaluator, drift detector, daily digest, market-data refresh, opportunity tick, macro ingestion, hypothesis tick, research weekly.

Why: pytest fixtures tear down cleanly with no orphan loops, warmup waits don't collide with assertions, suite is ~30% faster. **Production unchanged** — the env var is unset there. Don't set this flag in production.

If a test specifically needs to exercise a background loop's behaviour, either:
- Call the loop's inner function directly (e.g. `service.run_daily_tick`) and assert side effects, or
- Spin up a focused fixture that imports the loop module + invokes one cycle without going through lifespan.

## Why this works
Every service accesses the session via `from app.core import db as _db; _db.SessionLocal()`. This indirect reference resolves at call time — so the fixture's override is seen. **Do not refactor to `from app.core.db import SessionLocal`** at module top; it binds the original sessionmaker and breaks isolation.

## What is tested

| File | Coverage |
|---|---|
| `test_alerts.py` | webhook round-trip, destructive read, auth |
| `test_tickers.py` | CRUD, bulk, idempotent upsert, search, filter, webhook-driven creation, patch override |
| `test_asset_class.py` | pure heuristic unit tests |
| `test_market_data.py` | OHLCV cache, refresh path, providers |
| `test_kronos_validator.py` | eligibility check matrix |
| `test_kronos_routes.py` | `/v1/models`, `/v1/timeframes`, `/v1/eligibility` |
| `test_kronos_real_adapter.py` | adapter swap behaviour (no real torch import in CI) |
| `test_analysis.py` | submit_run + fan-out + ineligible + 429 surfaces |
| `test_analysis_import.py` | peer-import receiver, idempotency, loop avoidance |
| `test_concurrency.py` | lock+counter gate (no Semaphore TOCTOU) |
| `test_sync.py` | outbox enqueue (ticker + result kinds), drain, retry backoff, peer client mock |
| `test_watchlist.py` | CRUD + bulk add + auto-upsert into ticker registry |
| `test_schedule.py` | pure schedule helpers, runner tick (skip-disabled / skip-empty / 429-defer / actuals collect / actuals-failure-doesn't-fail-run / wake event) |
| `test_predictions.py` | explode_task, idempotent re-explode, backfill, FK cascade (PRAGMA-enforced on SQLite) |
| `test_predictions_comparison.py` | by-target, by-horizon, ?fields= preset+CSV, ?made_on_dow=, missing-data graceful |
| `test_labels.py` | EAV CRUD, JSON values (bool/list/dict), bulk upsert, ?labels= filter on watchlist |

## Not yet tested
- Alembic migrations themselves (run via deploy; local schema uses `create_all`).
- Real Postgres behavior (asyncpg-specific quirks, `ON CONFLICT` path).
- Concurrent upsert race conditions.
- Full E2E from frontend (no frontend yet).

## SQLite-vs-Postgres parity
The test fixture enables `PRAGMA foreign_keys=ON` on every aiosqlite connection so `ON DELETE CASCADE` behaves like Postgres. Migration files dialect-branch where SQLite can't match Postgres semantics (e.g. `ALTER COLUMN ... DROP NOT NULL`).
