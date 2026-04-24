# Architecture

Modular monorepo. Single FastAPI process. Modules are independent packages under `app/` with thin cross-imports (services, not routes). Each module owns its models, schemas, service, and routes.

## Layout
```
app/
  core/       config, db, auth — shared by every module
  alerts/     TradingView webhook ingestion (legacy endpoints, unversioned)
  tickers/    symbol registry, asset class inference, dropdown source
  market_data/ OHLCV providers, cache table, /v1/ohlcv
  api/        router aggregation (mounts v1 + legacy surfaces)
  main.py     FastAPI app factory + lifespan
migrations/   Alembic (source of truth for schema)
tests/        pytest, SQLite in-memory per test
```

## API surfaces
- **Legacy unversioned** (`/webhook`, `/alerts`): preserved for existing TradingView alert URL. Do not break.
- **`/v1/*`**: new modular surface. All new routes go here.

## Cross-module rules
- A module may import another module's **service** and **schemas**, never its routes.
- Only `app.core.*` is allowed to be imported everywhere.
- DB access goes through `app.core.db.SessionLocal` (indirect access via `from app.core import db as _db; _db.SessionLocal()`) to support test overrides. Direct `from app.core.db import SessionLocal` binds at import time and breaks test fixtures.

## Planned modules (not yet built)
`charts/`. See the plan at `/Users/shourjosmac/.claude/plans/you-are-helping-kind-graham.md`.

## Built modules
- `kronos/` — registry + validator + adapter stub. See [kronos.md](kronos.md).
- `analysis/` — job orchestrator (inline v1, arq-bound in Phase 5). See [analysis.md](analysis.md).
- `sync/` — outbox-based ticker replication to peer backend. See [sync.md](sync.md).

## Dual-backend topology

Two identical FastAPI instances (laptop primary on LAN, Railway replica always-on). Frontend picks which runs a given job; after completion, the runner pushes its touched tickers to the peer via `POST /v1/tickers` so both DBs retain a historic ticker catalog. OHLCV is refetched per job, not synced. Details: [sync.md](sync.md).

## Storage split: Postgres vs Redis
Railway Postgres = durable state. Railway Redis (to be added in Phase 4) = ephemeral queues.

| Data | Store | Why |
|---|---|---|
| Alerts, tickers, analysis jobs/results | Postgres | Durable, relational, Alembic-managed |
| OHLCV bars (cache) | Postgres `ohlcv_bars` | Range queries by ts, append-dedupe on `(symbol, interval, ts)` |
| Analysis job queue (Phase 4) | Redis (via `arq`) | Worker coordination, no durable-replay requirement |
| Rate-limit counters / last-price hot cache (future) | Redis | Ephemeral, TTL-native |

Do not use Redis for data that must survive a restart or that needs range queries.
