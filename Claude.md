# TradingView Analysis Platform

## What this is (60 seconds)

Personal trading-decision-support system for **one operator**. FastAPI backend runs Kronos candlestick predictions on a daily-scheduled watchlist; emits **opportunities** (rule-based BUY/SELL signals weighted by historical hit-rate); manually-logged **trades** close the loop with per-rule P\&L attribution. Bidirectional Tailscale sync between **laptop** (primary, has GPU-eligible inference) and **Railway** (always-on replica). Neumorphic React frontend on **Cloudflare Pages** at `https://tradingv-83b.pages.dev`. **Read** **[.claude/principles.md](.claude/principles.md)** **before making architectural changes** — it captures the load-bearing assumptions and trade-offs.

## Reading paths (start here based on your job)

| Job                 | Read in this order                                                                                                                             |
| :------------------ | :--------------------------------------------------------------------------------------------------------------------------------------------- |
| Onboarding fresh    | [principles.md](.claude/principles.md) → [architecture.md](.claude/architecture.md) → [roadmap-shipped.md](.claude/roadmap-shipped.md)         |
| Adding a feature    | [recipes.md](.claude/recipes.md) → the relevant module doc → [architecture.md](.claude/architecture.md)                                        |
| Fixing a prod bug   | [railway-deployment.md](.claude/railway-deployment.md) → the module → [backlog.md](.claude/backlog.md) + [tech\_debt.md](.claude/tech_debt.md) |
| Auditing a decision | [decisions/](.claude/decisions/) (ADRs) → [backlog.md](.claude/backlog.md) (RESOLVED entries)                                                  |
| Frontend only       | [frontend/README.md](.claude/frontend/README.md)                                                                                               |
| Defining a term     | [glossary.md](.claude/glossary.md)                                                                                                             |

## Entry points

- App: `app.main:app`
- Local: `uvicorn app.main:app --reload` (venv activated, env set)
- Deploy: Railway via Dockerfile + `tailscale-entrypoint.sh`. `railway.toml` declares the Dockerfile builder; the entrypoint runs Tailscale, then chains `alembic upgrade head && uvicorn ...` from the Dockerfile CMD. `Procfile` is unused on Railway. See [.claude/railway-deployment.md](.claude/railway-deployment.md).

## `.claude/` — module-specific docs

| You're touching...                                                                 | Read                                                           |
| :--------------------------------------------------------------------------------- | :------------------------------------------------------------- |
| Anything — always skim this first                                                  | [.claude/architecture.md](.claude/architecture.md)             |
| `app/core/` (config, db, auth)                                                     | [.claude/core.md](.claude/core.md)                             |
| `/webhook` or `/alerts`                                                            | [.claude/alerts.md](.claude/alerts.md)                         |
| `/v1/tickers*` or symbol registry                                                  | [.claude/tickers.md](.claude/tickers.md)                       |
| `/v1/ohlcv`, `/v1/intervals`, OHLCV cache, providers                               | [.claude/market\_data.md](.claude/market_data.md)              |
| `/v1/models`, `/v1/timeframes`, `/v1/eligibility`, Kronos validator/adapter        | [.claude/kronos.md](.claude/kronos.md)                         |
| `/v1/analysis/*`, job orchestration, fan-out, validator                            | [.claude/analysis.md](.claude/analysis.md)                     |
| `/v1/analysis/queue/*`, submit queue + worker                                      | [.claude/queue.md](.claude/queue.md)                           |
| `/v1/sync/*`, outbox, peer ticker replication, dual-backend                        | [.claude/sync.md](.claude/sync.md)                             |
| `/v1/watchlist*`, daily-run target set                                             | [.claude/watchlist.md](.claude/watchlist.md)                   |
| `/v1/schedule*`, daily forecast runner                                             | [.claude/schedule.md](.claude/schedule.md)                     |
| `/v1/predictions/by-target`, `/by-horizon`, `/backfill`, `prediction_points` table | [.claude/predictions.md](.claude/predictions.md)               |
| `/v1/accuracy/*`, `prediction_accuracy` + `drift_alerts` tables                    | [.claude/accuracy.md](.claude/accuracy.md)                     |
| `/v1/opportunities*`, signal generator, rule engine                                | [.claude/opportunities.md](.claude/opportunities.md)           |
| `/v1/trades*`, manual trade journal, P\&L attribution                              | [.claude/trades.md](.claude/trades.md)                         |
| `/v1/macro/*`, `macro_series` table, yfinance + FRED ingestion                     | [.claude/macro.md](.claude/macro.md)                           |
| `/v1/boards*` ("Watchlists" UI), casual ticker lists, `last_close`+`pct_1w` quotes | [.claude/boards.md](.claude/boards.md)                         |
| `/v1/hypotheses*`, `hypothesis` + `hypothesis_evaluation` tables, invalidator DSL  | [.claude/hypotheses.md](.claude/hypotheses.md)                 |
| `/v1/views*`, markdown view registry under `app/views/registry/`                   | [.claude/views.md](.claude/views.md)                           |
| Knowledge vault (Obsidian) + `tools/vault_indexer/` sidecar (port 8001)            | [.claude/vault.md](.claude/vault.md)                           |
| `hypothesis_node_links` table — pointer from hypothesis to vault path               | [.claude/vault.md](.claude/vault.md) (TradingView side)        |
| Telegram notifier, drift alerts, daily digest                                      | [.claude/notifications.md](.claude/notifications.md)           |
| `/v1/tickers/{sym}/labels*`, free-form ticker metadata                             | [.claude/labels.md](.claude/labels.md)                         |
| DB schema changes / new migration                                                  | [.claude/migrations.md](.claude/migrations.md)                 |
| Writing or debugging tests                                                         | [.claude/testing.md](.claude/testing.md)                       |
| Deploying / debugging Railway                                                      | [.claude/railway-deployment.md](.claude/railway-deployment.md) |
| Laptop (primary) backend setup                                                     | [.claude/laptop-setup.md](.claude/laptop-setup.md)             |
| `frontend/` (Vite + React SPA, deployed at <https://tradingv-83b.pages.dev>)       | [.claude/frontend/README.md](.claude/frontend/README.md)       |

## Cross-cutting docs

| Doc                                                      | Purpose                                                       |
| :------------------------------------------------------- | :------------------------------------------------------------ |
| [.claude/principles.md](.claude/principles.md)           | Guiding principles + active trade-offs + implicit assumptions |
| [.claude/recipes.md](.claude/recipes.md)                 | How-to cookbook for common changes                            |
| [.claude/glossary.md](.claude/glossary.md)               | Terms used across docs and code                               |
| [.claude/decisions/](.claude/decisions/)                 | Architecture Decision Records (ADRs)                          |
| [.claude/roadmap.md](.claude/roadmap.md)                 | What's next (forward-looking)                                 |
| [.claude/macro-workbench-brainstorm.md](.claude/macro-workbench-brainstorm.md) | Pre-plan: regime-aware research workbench (M-1..M-6 phases)   |
| [.claude/roadmap-shipped.md](.claude/roadmap-shipped.md) | What's shipped (archive)                                      |
| [.claude/backlog.md](.claude/backlog.md)                 | Deferred features / known gaps / operator unlocks             |
| [.claude/tech\_debt.md](.claude/tech_debt.md)            | Code cruft knowingly left in shipped code                     |

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

