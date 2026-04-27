# TradingView Analysis Platform

FastAPI backend that ingests TradingView alerts and (in-flight) runs Kronos candlestick models against selected tickers + timeframes. Modular: each feature is an independent package under `app/`.

## Entry points
- App: `app.main:app`
- Local: `uvicorn app.main:app --reload` (venv activated, env set)
- Deploy: Railway via Dockerfile + `tailscale-entrypoint.sh`. `railway.toml` declares the Dockerfile builder; the entrypoint runs Tailscale, then chains `alembic upgrade head && uvicorn ...` from the Dockerfile CMD. `Procfile` is unused on Railway. See [.claude/railway-deployment.md](.claude/railway-deployment.md).

## `.claude/` — read these when working on a specific area

| You're touching... | Read |
|---|---|
| Anything — always skim this first | [.claude/architecture.md](.claude/architecture.md) |
| `app/core/` (config, db, auth) | [.claude/core.md](.claude/core.md) |
| `/webhook` or `/alerts` | [.claude/alerts.md](.claude/alerts.md) |
| `/v1/tickers*` or symbol registry | [.claude/tickers.md](.claude/tickers.md) |
| `/v1/ohlcv`, `/v1/intervals`, OHLCV cache, providers | [.claude/market_data.md](.claude/market_data.md) |
| `/v1/models`, `/v1/timeframes`, `/v1/eligibility`, Kronos validator/adapter | [.claude/kronos.md](.claude/kronos.md) |
| `/v1/analysis/*`, job orchestration, fan-out, validator | [.claude/analysis.md](.claude/analysis.md) |
| `/v1/analysis/queue/*`, submit queue + worker | [.claude/queue.md](.claude/queue.md) |
| `/v1/sync/*`, outbox, peer ticker replication, dual-backend | [.claude/sync.md](.claude/sync.md) |
| `/v1/watchlist*`, daily-run target set | [.claude/watchlist.md](.claude/watchlist.md) |
| `/v1/schedule*`, daily forecast runner | [.claude/schedule.md](.claude/schedule.md) |
| `/v1/predictions/by-target`, `/by-horizon`, `/backfill`, `prediction_points` table | [.claude/predictions.md](.claude/predictions.md) |
| `/v1/accuracy/*`, `prediction_accuracy` + `drift_alerts` tables | [.claude/accuracy.md](.claude/accuracy.md) |
| `/v1/opportunities*`, signal generator, rule engine | [.claude/opportunities.md](.claude/opportunities.md) |
| `/v1/trades*`, manual trade journal, P&L attribution | [.claude/trades.md](.claude/trades.md) |
| Telegram notifier, drift alerts, daily digest | [.claude/notifications.md](.claude/notifications.md) |
| `/v1/tickers/{sym}/labels*`, free-form ticker metadata | [.claude/labels.md](.claude/labels.md) |
| DB schema changes / new migration | [.claude/migrations.md](.claude/migrations.md) |
| Writing or debugging tests | [.claude/testing.md](.claude/testing.md) |
| Deploying / debugging Railway | [.claude/railway-deployment.md](.claude/railway-deployment.md) |
| Laptop (primary) backend setup | [.claude/laptop-setup.md](.claude/laptop-setup.md) |
| `frontend/` (Vite + React SPA, deployed at https://tradingv-83b.pages.dev) | [.claude/frontend/README.md](.claude/frontend/README.md) |
| Multi-phase decision-tool roadmap (current scope) | [.claude/roadmap.md](.claude/roadmap.md) |
| Deferred features / known gaps / operator unlocks | [.claude/backlog.md](.claude/backlog.md) |
| Tech debt knowingly left in shipped code | [.claude/tech_debt.md](.claude/tech_debt.md) |

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
1. New project → add Postgres plugin → deploy repo. Builder: Dockerfile (declared in `railway.toml`).
2. Set `API_KEY` env var. `DATABASE_URL`/`PORT` are auto-injected.
3. Alembic runs at container start (entrypoint chains `alembic upgrade head && uvicorn ...`).
4. Optional: `TS_AUTHKEY` for Tailscale tunnel back to laptop, `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` for push alerts (both no-op when unset). Full env list in [.claude/railway-deployment.md](.claude/railway-deployment.md).
