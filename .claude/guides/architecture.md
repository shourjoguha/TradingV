# Architecture

Modular monorepo. Single FastAPI process. Modules are independent packages under `app/` with thin cross-imports (services, not routes). Each module owns its models, schemas, service, and routes.

## Layout
```
app/
  core/           config, db, auth — shared by every module
  alerts/         TradingView webhook ingestion (legacy endpoints, unversioned)
  tickers/        symbol registry, asset class inference, dropdown source
  market_data/    OHLCV providers, cache table, /v1/ohlcv; derived.py = IV/earnings (Phase 6)
  kronos/         model registry, validator, real adapter (vendored model)
  analysis/       job orchestrator, fan-out, 429 gate, peer-import receiver
  sync/           outbox-based ticker + result replication
  watchlist/      actively-tracked subset of tickers (daily-run target)
  schedule/       daily forecast runner config + asyncio loop
  predictions/    flat materialised forecast view + comparison endpoints
  accuracy/       prediction_accuracy + drift_alerts; evaluator + drift detector loops
  opportunities/  signal generator (rule engine over predictions + hit-rate)
  trades/         manual trade journal + per-rule P&L attribution
  notifications/  Telegram notifier + daily digest loop
  labels/         free-form EAV ticker metadata
  macro/          Macro Workbench signal layer (yfinance + FRED daily series, ratios on demand)
  api/            router aggregation (mounts v1 + legacy surfaces)
  main.py         FastAPI app factory + lifespan (9 background loops)
migrations/       Alembic (source of truth for schema)
tests/            pytest, SQLite in-memory per test
backups/          local snapshots + ROLLBACK.md (gitignored except docs)
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
| `kronos/` | Registry + validator + real adapter (vendored Kronos model) | [kronos.md](../modules/kronos.md) |
| `analysis/` | Job orchestrator. Receives peer-imported jobs idempotently. | [analysis.md](../modules/analysis.md) |
| `queue/` | Tier-1 in-process FIFO submit queue + single-flight worker. `POST /v1/analysis/run` returns 202 + queue_id. | [queue.md](../modules/queue.md) |
| `sync/` | Outbox-based replication: `kind='ticker'` + `kind='result'` rows drain to peer. | [sync.md](../modules/sync.md) |
| `watchlist/` | The actively-tracked symbol set. Daily scheduler iterates this. | [watchlist.md](../modules/watchlist.md) |
| `schedule/` | Singleton config row + asyncio runner loop in lifespan. Skip-weekends, completion-trigger. Enqueues via the submit queue (no inline run, no 429 retry). | [schedule.md](../modules/schedule.md) |
| `predictions/` | `prediction_points` flat table (auto-exploded from `result_json`) + `by-target`/`by-horizon` comparison endpoints. | [predictions.md](../modules/predictions.md) |
| `accuracy/` | `prediction_accuracy` (per-row error) + `drift_alerts` + evaluator + drift detector. Powers `/accuracy` dashboard. | [accuracy.md](../modules/accuracy.md) |
| `opportunities/` | Signal generator: hardcoded rules over predictions + accuracy hit-rate → `opportunities` table. | [opportunities.md](../modules/opportunities.md) |
| `trades/` | Manual trade journal + per-opportunity-rule P&L attribution. | [trades.md](../modules/trades.md) |
| `notifications/` | Telegram notifier (no-op when unconfigured) + daily digest loop. | [notifications.md](../modules/notifications.md) |
| `labels/` | Free-form EAV metadata on tickers (sector, capsize, etc.). Powers `?labels=k:v` filter on watchlist. | [labels.md](../modules/labels.md) |
| `macro/` | Macro Workbench signal layer: `macro_series` table, yfinance + FRED providers, `/v1/macro/{series,ratio,refresh}`, daily ingestion lifespan. Foundation for the regime-aware research workbench. | [macro.md](../modules/macro.md) |
| `the_street/` | Read-only HTTP wrapper over `tools/the_street/query.py` — `/v1/the-street/{snapshots,ticker/{sym},tier/{1\|2\|3},politician/{name}}`. Backs the `/the-street` page + Ticker Hub `StreetCard`. No DB writes; reads `<vault>/The Street/snapshots/`. | (see `<vault>/The Street/_index.md`) |
| `vault/` | httpx-forwarder to the vault-indexer sidecar on port 8001. Surfaces `/v1/vault/{search,folder-context,node/{path}}` so the frontend never has to hit the indexer port directly. Read-only; maps 504/502 when sidecar offline. | (thin proxy — see `tools/vault_indexer/app.py`) |
| `admin/` | Loop registry, `app_settings` cascade, `process_status` writes, Anthropic kill-switch + monthly cap. Surfaces `/v1/admin/{loops,settings}` for the new tabbed Admin UI (Phase 4 of the cost-aware iteration). | [admin.md](../modules/admin.md) |
| `earnings/` | Rolling earnings calendar (roster ∪ Street tier1+2, capped 150, 90d TTL). yfinance + NASDAQ providers; EDGAR 8-K Item 2.02 confirm. Surfaces `/v1/earnings/{upcoming, ticker}`. Backs the IR YouTube channel poller's earnings-trigger gate. | [earnings.md](../modules/earnings.md) |
| `ticker_review/` | Laptop-only `ticker_review_queue` table. Fed by Stage 1 (Qwen2-VL) unknown-ticker emissions from video ingest **AND TV-context note/idea/screenshot/event ingest (Phase 1 of tv-context-decision-engine-enrichment, 2026-05-17)**. Surfaces `/v1/ticker-review/{queue, {id}/resolve}` for the Today strip; Sunday markdown digest to `<vault>/Topics/_ticker-review-queue.md` via `ticker_review_digest` lifespan loop. Resolve chains atomically to watchlist or board add. 90-day re-eligibility window after dismiss. | [ticker_review.md](../modules/ticker_review.md) |
| `tv_context/` | Polymorphic `tv_context_items` table with `kind` discriminator (webhook/note/idea/event/screenshot). Per-kind retention sweep, vision summarization on screenshots, OCR-driven ticker auto-extract. **Now fans out unknown tickers to `ticker_review_queue`** and **stamps `attention_score` on every new rec via `rx/`** + **feeds `tv_context_count_since` / `tv_context_stance_count_since` invalidator DSL ops on `hypotheses/`** (the 3-phase decision-engine enrichment shipped 2026-05-17). | [tv_context.md](../modules/tv_context.md) |
| `hypotheses/` | Hypothesis CRUD + invalidator DSL + daily `_hyp_tick` evaluation loop. 7 ops: `ratio_below_sma`, `series_above_threshold`/`below_threshold`, `series_change_pct`, `manual`, `tv_context_count_since`, `tv_context_stance_count_since`. The last two read `HypothesisTVContextLink` rows so operator-flagged screenshots/notes drive auto-invalidation. | [hypotheses.md](../modules/hypotheses.md) |
| `research/` | Skill-driven stress-test pipeline (`/v1/research/ask` → Claude Sonnet with vault grounding). Phase-4 gate: `requires_tv_context=True` short-circuits when no recent items exist. Outputs land in `<vault>/Research/<date>-<slug>.md`. | [research.md](../modules/research.md) |
| `rx/` | Finance recommendation surface (TradingV-exclusive per D-045). `recommendations` table + `/v1/rx/recs/{list, {id}, disposition, snooze}`. **`attention_score FLOAT NULL` + `attention_breakdown JSON NULL`** stamped at create from `tv_context_signal.compute_attention_for_rec` — closes the "operator screenshotted NVDA but the rec engine ignored it" gap. | [rx.md](../modules/rx.md) |
| Vault video-vision (sidecar) | Three-stage extraction in `tools/vault_indexer/ingest/`: scene-detect frames → Tesseract OCR → optional Qwen2-VL MLX captions → structured chart references (chart_type, timeframe, tickers). Per-channel toggles in `_channel.yaml` (`vision.enabled` / `semantic_captions` / `chart_extraction.enabled`). Auto-enriches channel `_index.md` with rolling chart-reference table consumed by `/folder-context`. Unknown-ticker hits flow to `app/ticker_review/`. | [video_vision.md](../modules/video_vision.md) |

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

## ~~Dual-backend topology~~ — single backend since 2026-05-17

> **Status:** Railway permanently shut down per [ADR 018](../decisions/018-railway-shutdown.md). Frontend has no backend toggle; `BackendId = 'laptop'` is a single-member union. `app/sync/` module retained dormant — no peer URL is set, so sync-outbox rows accumulate but never push. Section below preserved as historical reference.

~~Two identical FastAPI instances (laptop primary on LAN, Railway replica always-on).~~ Frontend used to pick which ran a given job; after completion, the runner pushed its touched tickers AND a full job snapshot to the peer via `POST /v1/tickers` + `POST /v1/analysis/import` so both DBs retained history. OHLCV was refetched per job, not synced. Details: [sync.md](../modules/sync.md).

~~**Bidirectional sync is live**.~~ Phase B1+B2 added a Tailscale tunnel from Railway back to the laptop. As of 2026-05-17 the Railway side is offline; only the outbox-write code path runs and the rows are inert.

## Storage split: Postgres vs Redis
Postgres = durable state. Redis (deferred) = ephemeral queues.

| Data | Store | Why |
|---|---|---|
| Alerts, tickers, analysis jobs/tasks | Postgres | Durable, relational, Alembic-managed |
| OHLCV bars (cache) | Postgres `ohlcv_bars` | Range queries by ts, append-dedupe on `(symbol, interval, ts)` |
| `prediction_points` (forecast materialised view) | Postgres | Indexed lookups by (target_date, ticker), (made_on, ticker) |
| `prediction_accuracy`, `drift_alerts` | Postgres | Per-row error history; aggregated at query time |
| `opportunities`, `trades` | Postgres | Signal lifecycle + manual journal |
| `ticker_market_data` (IV percentile, earnings) | Postgres | Phase 6 options runway, daily refresh |
| `sync_outbox`, `schedule_config`, `watchlist`, `ticker_labels` | Postgres | All durable config + queue state |
| Analysis job queue (deferred) | Redis (via `arq`) | Worker coordination when inline-dispatch becomes a bottleneck |
| Rate-limit counters / last-price hot cache (future) | Redis | Ephemeral, TTL-native |

Do not use Redis for data that must survive a restart or that needs range queries.

## In-process schedulers + background tasks

The `app.main` lifespan starts these tasks (all cancellation-safe; tolerant of missing config — they no-op rather than crash when prerequisites are absent):

1. **`Base.metadata.create_all`** — first-boot fallback (Alembic is the source of truth in prod).
2. **Kronos adapter activation** if `KRONOS_ENABLED=true`.
3. **`sync_service.drain_outbox()`** — best-effort drain of pending rows from a prior process.
4. **`sync_service.purge_loop()`** — hourly cleanup of completed outbox rows older than `OUTBOX_RETENTION_DAYS` (default 7).
5. **`schedule.runner.start()`** — daily forecast runner (idle until `schedule_config.enabled=true`). On Railway with `RAILWAY_FALLBACK_ENABLED=true` ALSO spawns `_fallback_loop()`.
6. **`accuracy.service.evaluator_loop()`** — hourly: evaluate elapsed predictions whose actuals exist in `ohlcv_bars`. See [accuracy.md](../modules/accuracy.md).
7. **`accuracy.drift.detector_loop()`** — every 6h: scan for (ticker, horizon, model) pairs whose recent MAPE has degraded past threshold. Posts to Telegram on flag. See [accuracy.md](../modules/accuracy.md).
8. **`notifications.digest.digest_loop()`** — sleeps until `DIGEST_HOUR_UTC`, posts daily summary (top opportunities + open drift alerts + schedule snapshot) to Telegram.
9. **`market_data.derived.market_data_loop()`** — daily: refresh per-watchlist IV + earnings dates into `ticker_market_data`. Phase 6 runway data; no UI yet.
10. **Opportunities tick** (inline `_opps_loop` in `app/main.py`) — hourly: `generate_for_predictions()` then `expire_stale()`.
11. **`queue.worker.worker_loop()`** — single-flight FIFO drain of `submit_queue`. Each pending row → `analysis.service.submit_run` → mark done. Boot calls `queue.service.reset_stuck_on_boot()` first to recover from crashed mid-job state. See [analysis.md](../modules/analysis.md) for the queue contract; deferred-decision tracking in [tech_debt.md](../status/tech_debt.md).

## Network topology + Tailscale

Railway uses a Dockerfile (not Railpack) so it can install Tailscale. On boot, `tailscale-entrypoint.sh` joins the operator's tailnet (userspace networking — no `CAP_NET_ADMIN` needed) when `TS_AUTHKEY` is set. With Tailscale up, `PEER_API_URL` on Railway points at the laptop's MagicDNS hostname (e.g. `laptop-name.tailxxxxx.ts.net:8000`) — laptop is reachable from Railway without exposing it publicly. See [railway-deployment.md](railway-deployment.md) for setup.

## CORS

`app/main.py` adds `CORSMiddleware`. Allow-list driven by `FRONTEND_ORIGIN` env var (CSV of absolute origins). When unset, falls back to `localhost:{3000,5173}` so local dev works zero-config.

## Frontend

`frontend/` is a Vite + React + TypeScript SPA that talks to this backend over `X-API-Key`. Single-user, no SSR. Production deployment at **`https://tradingv-83b.pages.dev`** (Cloudflare Pages, auto-deploys on push to `main`). Local dev uses a Vite proxy to sidestep CORS (`/v1` + `/health` → `localhost:8000`); the Railway toggle in the browser uses `CORSMiddleware` (already shipped) keyed off `FRONTEND_ORIGIN`. For stack, layout, and per-area docs see [frontend/README.md](../frontend/README.md). For the cloud port specifics see `/Users/shourjosmac/.claude/plans/cloudflare-pages-port.md`.
