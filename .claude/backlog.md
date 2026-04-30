# Backlog

Deferred decisions and known-but-unaddressed gaps. Each entry: what, why deferred, options considered, current state, trigger to revisit.

> **Tech debt** (cruft we knowingly left in shipped code) lives separately at [.claude/tech_debt.md](tech_debt.md). Backlog is for *features*; tech_debt is for *code chores*.

---

## Decision-tool roadmap — see [.claude/roadmap.md](roadmap.md)

**Status (2026-04-30):** Phases 0-6 SHIPPED. All backend tables + lifespan loops + endpoints + frontend pages live. 254 tests pass. Unlock #2 RESOLVED via self-healing OHLCV fetch (ADR-010); scheduler mid-tick PUT race RESOLVED (ADR-011). Telegram still dormant — see Unlock #1.

| Phase | Title | Status |
|---|---|---|
| 0 | Snapshot (rollback safety) | ✅ tag `v1.0-pre-trust-sprint` |
| 1.1 | prediction_accuracy + evaluator | ✅ live |
| 1.2 | /accuracy frontend | ✅ live |
| 1.3 | drift detection + Telegram alerts (backend) | ✅ live (Telegram dormant — see unlock #1) |
| 2.1 | empty states | ✅ live |
| 2.2 | lightweight-charts v5 upgrade | DEFERRED — not on critical path |
| 3.1 | opportunities + signal generator | ✅ live (self-healing OHLCV — see unlock #2 RESOLVED) |
| 3.2 | /opportunities frontend | ✅ live |
| 4 | daily Telegram digest | ✅ live (dormant until Telegram set up) |
| 5 | trade journal (backend + frontend) | ✅ live |
| 6 | options runway data layer | ✅ live (silently collecting IV + earnings daily) |

Roadmap doc has locked decisions (metrics, drift threshold, channel, sequencing). Update there, not here.

---

## Unlock #1 — Telegram bot setup (~5 min) — DEFERRED

**What:** Drift alerts + daily digest are coded + live but no-op until `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` env vars are set on Railway (and optionally laptop). Notifier logs once at startup that it's not configured, then stays silent. Code is deploy-safe in this state.

**Steps when revisiting:**
1. On Telegram, DM @BotFather → `/newbot` → follow prompts → save the token (looks like `123456:ABC-DEF...`).
2. DM your new bot any message (forces a chat to exist).
3. `curl https://api.telegram.org/bot<TOKEN>/getUpdates` → in the JSON response, copy `result[0].message.chat.id` (an integer).
4. Railway dashboard → service → Variables → add:
   - `TELEGRAM_BOT_TOKEN=<token>`
   - `TELEGRAM_CHAT_ID=<chat_id>`
5. Save → Railway redeploys → drift alerts post on next detection tick (every 6h); daily digest fires at `DIGEST_HOUR_UTC` (default 12 = 8 AM ET).
6. Test: `curl -X POST -H "X-API-Key: <RAILWAY_KEY>" https://tradingv-production.up.railway.app/v1/accuracy/drift/detect` — if any drift exists you'll get the message instantly.

**Files involved:** `app/notifications/telegram.py`, `app/notifications/digest.py`, `app/accuracy/drift.py`, `app/core/config.py`.

**Trigger to revisit:** when you want push notifications instead of polling the dashboard.

---

## Unlock #2 — Self-healing OHLCV fetch  ✅ RESOLVED

**Resolution (2026-04-30):** Option A landed. Accuracy evaluator's hourly tick now calls `md_service.refresh()` when a pending prediction's actual is missing — deduped per `(ticker, interval)` per tick, capped per `(ticker, interval, target_ts)` lifetime via `ohlcv_fetch_misses` (max 24 attempts ≈ one day at hourly cadence). Same lazy refresh added to the analysis pipeline (`_process_task`) so cold-start intervals like 1h get warmed automatically. See [decisions/010](decisions/010-self-healing-ohlcv-fetch.md).

Baseline (`made_on` close) for opportunities is still cache-only today; same approach can extend there if needed (low priority — usually present once analysis lazy-refresh ran).

**Files:** `app/accuracy/service.py::evaluate_pending` + `_try_refresh_actual`, `app/accuracy/models.py::OhlcvFetchMiss`, `migrations/versions/0018_ohlcv_fetch_misses.py`, `app/analysis/service.py::_process_task`.

---

---

## Charting library — lightweight-charts v5 chosen over Plotly (deliberation)

**Decision (2026-04-27):** Stay on lightweight-charts; upgrade v4 → v5 in Phase 2.2. Plotly evaluated and rejected for primary OHLC charting.

Reasons:
- lightweight-charts is TradingView's own lib, purpose-built for OHLC + overlays. v5 added crosshair sync, drawing tools, multi-pane.
- ~50 KB vs Plotly ~3 MB gzipped. Bundle bloat unacceptable for a single-user tool that doesn't need scientific viz.
- Plotly reserved for the future options chapter (vol surfaces, Greeks plots, 3D) — different problem.

Trigger to revisit: building options strategy generator or wanting non-OHLC scientific overlays.

---

## Cloud frontend hosting (Lovable rejected → Cloudflare Pages)  ✅ RESOLVED

**Resolution (2026-04-27):** Lovable evaluated, rejected — no existing-repo import, no build-time `VITE_*` env var UI, no per-PR preview URLs, no header/redirect config, AI editor mutates source. Switched to **Cloudflare Pages** at `https://tradingv-83b.pages.dev`. Plan: `/Users/shourjosmac/.claude/plans/cloudflare-pages-port.md`. New artifacts: `frontend/public/_redirects` (SPA fallback) + CF dashboard config + Railway `FRONTEND_ORIGIN`. No `frontend/src/` changes.

---

## Reverse-direction sync: Railway → Laptop  ✅ RESOLVED

**Resolution:** Phase B1+B2 of backlog rollout. Tailscale chosen (Option A from the original three).

How it works in production:
- `Dockerfile` installs Tailscale; `tailscale-entrypoint.sh` runs `tailscaled --tun=userspace-networking --outbound-http-proxy-listen=:1055`, then `tailscale up` joins the operator's tailnet as ephemeral host `tradingv-railway-N`.
- Container exports `HTTP_PROXY=http://127.0.0.1:1055` + `HTTPS_PROXY=http://127.0.0.1:1055` + `NO_PROXY=localhost,127.0.0.1,postgres.railway.internal,.railway.internal,.railway.app`. httpx + urllib + requests auto-route through tailscaled.
- `PEER_API_URL=http://<laptop-tailnet-ip>:8000` (note port — see lessons below).
- `PEER_API_KEY=<laptop's API_KEY>`.

Verified: Railway-originated job pushes both `kind='ticker'` and `kind='result'` outbox rows; laptop receives the imported job (origin='peer'), explodes prediction_points; comparison endpoints on laptop see the data.

**Lessons learned during rollout** (worth a re-read if anyone touches the tunnel):
1. `[deploy].startCommand` in `railway.toml` BYPASSES the Docker ENTRYPOINT — the entrypoint script never ran. Removed startCommand to let ENTRYPOINT chain into CMD.
2. `tailscaled --tun=userspace-networking` does NOT install kernel routes — direct connection to `100.x.y.z` hangs. Must use the HTTP proxy.
3. `ALL_PROXY=socks5://...` makes httpx import `socksio` (not in requirements). Don't set ALL_PROXY; HTTP_PROXY/HTTPS_PROXY cover both protocols.
4. `PEER_API_URL` MUST include the port (`:8000`); without it requests go to port 80 and 502 from the proxy.

---

## sync_outbox cleanup task  ✅ RESOLVED

**Resolution:** Phase C1. `purge_loop()` lifespan task ticks hourly, deletes rows where `completed_at < now() - OUTBOX_RETENTION_DAYS` (default 7). Pending rows are never touched. Tested in `tests/test_outbox_cleanup.py`.

---

## asset_class reconciliation  ✅ RESOLVED

**Resolution:** Phase C3. `tickers_svc.upsert_ticker` enqueues a `kind='ticker'` sync row when asset_class transitions from `unknown` (or empty) to a real class. Same code path as the existing ticker push — receiver upserts via `POST /v1/tickers`. Tested in `tests/test_sync.py`.

---

---

## Railway-fallback inference when laptop down  ✅ RESOLVED

**Resolution:** Phase B4. Lifespan task `_fallback_loop()` in `app/schedule/runner.py` ticks every 30 min on Railway when `RAILWAY_FALLBACK_ENABLED=true`. Per-symbol dedupe via `prediction_points`. Configurable `fallback_offset_hours` on `schedule_config` (default 6h). Tested in `tests/test_schedule_fallback.py`.

---

## Watchlist + schedule_config + labels replication to Railway  ✅ RESOLVED

**Resolution:** Phase B3. `sync_outbox.kind` extended with `'watchlist' | 'schedule' | 'label'`. Each external CRUD on watchlist / schedule / label enqueues a row; drain dispatches to peer `POST /v1/{watchlist,schedule,labels}/import`. Receivers bypass the enqueue path so imports don't loop. Tested in `tests/test_sync_replication.py`.

---

## Job submission queue (replace 5-min poll + eliminate 429s)  ✅ RESOLVED

**Resolution (2026-04-27):** Tier-1 in-process queue shipped — see [.claude/queue.md](queue.md). `submit_queue` table (migration 0017) + single-flight `worker.worker_loop` lifespan task. `POST /v1/analysis/run` returns 202 with `queue_id`; schedule runner enqueues like any other caller. Crash recovery via `reset_stuck_on_boot()`. Cancellation supported on `pending` items only. Frontend: toast on submit, queue widget on Dashboard, queue card with cancel buttons on AnalysisJobs page. 245 tests pass.

**Tier 2 (Redis + arq workers)** deferred — see [.claude/tech_debt.md](tech_debt.md). Trigger to revisit: sustained queue depth > 5 OR GPU inference lands.

---

## Trading-day filter per asset_class  ✅ RESOLVED

**Resolution:** Phase C2. `app/market_data/calendar.py::is_trading_day(asset_class, date)`: stocks/ETFs/forex/futures = Mon-Fri; crypto/commodity = always; unknown = always (permissive fallback). Scheduler partitions watchlist by asset class on each tick. Tested in `tests/test_calendar.py`.

---

## CORS middleware for browser-side Railway toggle  ✅ RESOLVED

**Resolution:** `CORSMiddleware` wired in `app/main.py`. Allow-list driven by `FRONTEND_ORIGIN` env var (CSV of absolute origins). When unset, falls back to `http://localhost:{3000,5173}` so local dev works out of the box. Set `FRONTEND_ORIGIN=https://<your-app>.lovable.dev` on Railway when frontend deploys.

---

## Scheduler loses today's slot if PUT /v1/schedule lands during execution window  ✅ RESOLVED

**Resolution (2026-04-30):** Moved the `next_run_at` advancement out of `_tick` (which computed against a stale config snapshot taken at tick start) and into `record_run`. `record_run` now takes `advance_now` (an instant) instead of `advance_to` (a precomputed value) and recomputes against the freshly-loaded config row. A PUT that lands during a tick is honored on the way out — no more lost slots, no `is_running` flag needed. See [decisions/011](decisions/011-schedule-mid-tick-put-race.md).

**Files:** `app/schedule/service.py::record_run`, `app/schedule/runner.py::_tick`, plus regression tests in `tests/test_schedule.py`.

---

## How to add an entry

Use the same structure: **What** / **Status** / **Why deferred** (or **Open**) / **Trigger to revisit** / **Implementation pointers**. Include the key files involved so future-you doesn't have to re-derive context.
