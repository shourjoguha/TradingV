# Testing

`pytest` + `pytest-asyncio` (auto mode) + `httpx.AsyncClient` against ASGI transport. DB = SQLite in-memory per test via `aiosqlite`.

## Running
```
source venv/bin/activate
python -m pytest
```

## Fixture pattern (`tests/conftest.py`)
The `client` fixture monkey-patches `app.core.db.engine` and `app.core.db.SessionLocal` to a fresh in-memory SQLite engine, creates all tables via `Base.metadata.create_all`, then imports `app.main:app` and returns an `AsyncClient`. Each test gets a fully isolated DB.

## Why this works
Every service accesses the session via `from app.core import db as _db; _db.SessionLocal()`. This indirect reference resolves at call time — so the fixture's override is seen. **Do not refactor to `from app.core.db import SessionLocal`** at module top; it binds the original sessionmaker and breaks isolation.

## What is tested
- `tests/test_alerts.py` — webhook round-trip, destructive read, auth.
- `tests/test_tickers.py` — CRUD, bulk, idempotent upsert, search, filter, webhook-driven ticker creation, patch override.
- `tests/test_asset_class.py` — pure heuristic unit tests.

## Not yet tested
- Alembic migrations themselves (run via deploy; local schema uses `create_all`).
- Real Postgres behavior (asyncpg-specific quirks, `ON CONFLICT` path).
- Concurrent upsert race conditions.
