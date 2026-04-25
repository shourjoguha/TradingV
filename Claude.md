# TradingView Analysis Platform

FastAPI backend that ingests TradingView alerts and (in-flight) runs Kronos candlestick models against selected tickers + timeframes. Modular: each feature is an independent package under `app/`.

## Entry points
- App: `app.main:app`
- Local: `uvicorn app.main:app --reload` (venv activated, env set)
- Deploy: Railway. `Procfile` → `release: alembic upgrade head` + `web: uvicorn app.main:app ...`.

## `.claude/` — read these when working on a specific area

| You're touching... | Read |
|---|---|
| Anything — always skim this first | [.claude/architecture.md](.claude/architecture.md) |
| `app/core/` (config, db, auth) | [.claude/core.md](.claude/core.md) |
| `/webhook` or `/alerts` | [.claude/alerts.md](.claude/alerts.md) |
| `/v1/tickers*` or symbol registry | [.claude/tickers.md](.claude/tickers.md) |
| `/v1/ohlcv`, `/v1/intervals`, OHLCV cache, providers | [.claude/market_data.md](.claude/market_data.md) |
| `/v1/models`, `/v1/timeframes`, `/v1/eligibility`, Kronos validator/adapter | [.claude/kronos.md](.claude/kronos.md) |
| `/v1/analysis/*`, job orchestration, fan-out, 429 gate | [.claude/analysis.md](.claude/analysis.md) |
| `/v1/sync/*`, outbox, peer ticker replication, dual-backend | [.claude/sync.md](.claude/sync.md) |
| DB schema changes / new migration | [.claude/migrations.md](.claude/migrations.md) |
| Writing or debugging tests | [.claude/testing.md](.claude/testing.md) |
| Deploying / debugging Railway | [.claude/railway-deployment.md](.claude/railway-deployment.md) |
| Laptop (primary) backend setup | [.claude/laptop-setup.md](.claude/laptop-setup.md) |
| Deferred decisions / known gaps | [.claude/backlog.md](.claude/backlog.md) |

Read only what you need. Each file is < 1 screen and describes one concern: the module's purpose, its schema, the decisions that aren't obvious from code, and the known gaps. When in doubt, `architecture.md` has the map.

## Setup (local)
1. `python3 -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. Export `DATABASE_URL` (Postgres or `sqlite+aiosqlite:///./dev.db`) and `API_KEY`.
4. `alembic upgrade head` (or rely on `create_all` in the lifespan for first boot).
5. `uvicorn app.main:app --reload`
6. Tests: `python -m pytest`.

For the **laptop (primary) backend** with dockerized Postgres on 5439 + peer sync to Railway, see [.claude/laptop-setup.md](.claude/laptop-setup.md).

## Setup (Railway)
1. New project → add Postgres plugin → deploy repo.
2. Set `API_KEY` env var. `DATABASE_URL`/`PORT` are auto-injected.
3. Alembic runs via `release:` in the Procfile.
