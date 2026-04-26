# Architecture

Modular monorepo. Single FastAPI process. Modules are independent packages under `app/` with thin cross-imports (services, not routes). Each module owns its models, schemas, service, and routes.

## Layout
```
app/
  core/         config, db, auth — shared by every module
  alerts/       TradingView webhook ingestion (legacy endpoints, unversioned)
  tickers/      symbol registry, asset class inference, dropdown source
  market_data/  OHLCV providers, cache table, /v1/ohlcv
  kronos/       model registry, validator, real adapter (vendored model)
  analysis/     job orchestrator, fan-out, 429 gate, peer-import receiver
  sync/         outbox-based ticker + result replication
  watchlist/    actively-tracked subset of tickers (daily-run target)
  schedule/     daily forecast runner config + asyncio loop
  predictions/  flat materialised forecast view + comparison endpoints
  labels/       free-form EAV ticker metadata
  api/          router aggregation (mounts v1 + legacy surfaces)
  main.py       FastAPI app factory + lifespan
migrations/     Alembic (source of truth for schema)
tests/          pytest, SQLite in-memory per test
```

## API surfaces
- **Legacy unversioned** (`/webhook`, `/alerts`): preserved for existing TradingView alert URL. Do not break.
- **`/v1/*`**: new modular surface. All new routes go here.

## Cross-module rules
- A module may import another module's **service** and **schemas**, never its routes.
- Only `app.core.*` is allowed to be imported everywhere.
- DB access goes through `app.core.db.SessionLocal` (indirect access via `from app.core import db as _db; _db.SessionLocal()`) to support test overrides. Direct `from app.core.db import SessionLocal` binds at import time and breaks test fixtures.

## Module map (built)

| Module | Purpose | Doc |
|---|---|---|
| `kronos/` | Registry + validator + real adapter (vendored Kronos model) | [kronos.md](kronos.md) |
| `analysis/` | Job orchestrator (inline v1, arq-bound when frontend ships). Receives peer-imported jobs idempotently. | [analysis.md](analysis.md) |
| `sync/` | Outbox-based replication: `kind='ticker'` + `kind='result'` rows drain to peer. | [sync.md](sync.md) |
| `watchlist/` | The actively-tracked symbol set. Daily scheduler iterates this. | [watchlist.md](watchlist.md) |
| `schedule/` | Singleton config row + asyncio runner loop in lifespan. Skip-weekends, completion-trigger, retry-on-429. | [schedule.md](schedule.md) |
| `predictions/` | `prediction_points` flat table (auto-exploded from `result_json`) + `by-target`/`by-horizon` comparison endpoints. | [predictions.md](predictions.md) |
| `labels/` | Free-form EAV metadata on tickers (sector, capsize, etc.). Powers `?labels=k:v` filter on watchlist. | [labels.md](labels.md) |

## Daily forecast pipeline (cross-module flow)

```
                  ┌──────────────┐
                  │  watchlist   │  <── frontend CRUD
                  └──────┬───────┘
                         │ symbols
                         ▼
                  ┌──────────────┐
   schedule_config│   schedule   │  <── PUT /v1/schedule (enabled, run_at_local, ...)
       (singleton)│    runner    │
                  └──────┬───────┘
                         │ submit_run(watchlist × intervals × model_ids)
                         ▼
                  ┌──────────────┐         ┌──────────────┐
                  │   analysis   │ ──────▶ │ predictions  │ explode_task
                  │ _process_task│         │  (flat table)│
                  └──────┬───────┘         └──────────────┘
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
       refresh      enqueue       enqueue
       OHLCV       (ticker)       (result)
       (actuals)        │              │
                        ▼              ▼
                ┌────────────────────────┐
                │     sync outbox        │
                │  drain → peer backend  │
                └────────────────────────┘
                         │ POST /v1/analysis/import
                         ▼
                  Peer's analysis service
                  origin='peer' (no re-replication)
                         │
                         ▼
                  Peer's predictions service
                  explode_imported_tasks()
```

Comparison endpoints (`/v1/predictions/by-target`, `/v1/predictions/by-horizon`) read from `prediction_points` + `ohlcv_bars` and join in-process.

## Dual-backend topology

Two identical FastAPI instances (laptop primary on LAN, Railway replica always-on). Frontend picks which runs a given job; after completion, the runner pushes its touched tickers AND a full job snapshot to the peer via `POST /v1/tickers` + `POST /v1/analysis/import` so both DBs retain history. OHLCV is refetched per job, not synced. Details: [sync.md](sync.md).

v1 ships with **Laptop → Railway** sync only (one-way). Reverse direction deferred — see [backlog.md](backlog.md).

## Storage split: Postgres vs Redis
Postgres = durable state. Redis (deferred) = ephemeral queues.

| Data | Store | Why |
|---|---|---|
| Alerts, tickers, analysis jobs/tasks | Postgres | Durable, relational, Alembic-managed |
| OHLCV bars (cache) | Postgres `ohlcv_bars` | Range queries by ts, append-dedupe on `(symbol, interval, ts)` |
| `prediction_points` (forecast materialised view) | Postgres | Indexed lookups by (target_date, ticker), (made_on, ticker) |
| `sync_outbox`, `schedule_config`, `watchlist`, `ticker_labels` | Postgres | All durable config + queue state |
| Analysis job queue (deferred) | Redis (via `arq`) | Worker coordination when inline-dispatch becomes a bottleneck |
| Rate-limit counters / last-price hot cache (future) | Redis | Ephemeral, TTL-native |

Do not use Redis for data that must survive a restart or that needs range queries.

## In-process schedulers + background tasks

The `app.main` lifespan starts:
1. **`Base.metadata.create_all`** — first-boot fallback (Alembic is the source of truth in prod).
2. **Kronos adapter activation** if `KRONOS_ENABLED=true`.
3. **`sync_service.drain_outbox()`** — best-effort drain of pending rows from a prior process.
4. **`schedule.runner.start()`** — single asyncio task running the daily-forecast loop. Idle until `schedule_config.enabled=true`.

All four are tolerant of missing config (drain no-ops without `PEER_API_URL`; scheduler stays asleep if disabled).
