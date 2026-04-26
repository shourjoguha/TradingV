# Backlog

Deferred decisions and known-but-unaddressed gaps. Each entry: what, why deferred, options considered, current state, trigger to revisit.

---

## Reverse-direction sync: Railway → Laptop

**What:** When the model runs on Railway, push the resulting job snapshot back to the laptop DB so both backends mirror history.

**Status:** Deferred (Option C). Forward direction (Laptop → Railway) is live and verified end-to-end. Reverse direction is no-op: Railway's `PEER_API_URL` is intentionally unset, so its outbox skips enqueue.

**Why deferred:** Reverse direction needs the laptop reachable from Railway. Three paths considered:

| Option | Security | Railway-side work | Laptop-side work | Verdict |
|---|---|---|---|---|
| A — Tailscale on Railway (init script installs `tailscaled`, joins tailnet) | Strongest. Laptop unreachable to anyone outside tailnet. | ~30 min: Dockerfile/start script + `TS_AUTHKEY` env var | `tailscale up` (already easy) | **Preferred when revisited** |
| B — Cloudflared `trycloudflare` quick tunnel | Public URL, gated only by `API_KEY`. Brute-force infeasible but URL leak = recon target. | None | `cloudflared tunnel --url localhost:8000` | Acceptable interim |
| C — Skip (current) | n/a | n/a | n/a | Chosen for v1 |

**Trigger to revisit:** When the frontend ships and operator wants to inference on Railway as primary path (e.g. laptop closed). Or when Railway-originated TradingView webhooks should sync history back.

**Implementation pointers (when ready):**
- Forward direction already wired: `app/analysis/service.py::_process_job` enqueues both `kind='ticker'` and `kind='result'` rows.
- Receiver `POST /v1/analysis/import` already deployed on both backends — idempotent, tagged `origin='peer'`, loop-avoidant.
- Only blocker is network reachability + setting `PEER_API_URL` on Railway.

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

## Completion-trigger queue (replace 5-min retry poll)

**What:** Today, scheduled runs that hit `AtCapacityError` retry every 5 minutes. Instead, the in-flight job's `_process_job` end could check for "scheduled run pending" flag and fire immediately.

**Status:** Hybrid-approach already partially in Phase 2 plan — completion-trigger included alongside 5-min poll.

**Trigger to revisit:** If 5-min poll becomes a real bottleneck (i.e. operator triggers many manual jobs, scheduled run keeps deferring beyond 30 min).

**Implementation:** Replace poll loop with a proper task queue (asyncio Queue or persistent queue table). Multi-job sequencing.

---

## Trading-day filter per asset_class  ✅ RESOLVED

**Resolution:** Phase C2. `app/market_data/calendar.py::is_trading_day(asset_class, date)`: stocks/ETFs/forex/futures = Mon-Fri; crypto/commodity = always; unknown = always (permissive fallback). Scheduler partitions watchlist by asset class on each tick. Tested in `tests/test_calendar.py`.

---

## CORS middleware for browser-side Railway toggle  ✅ RESOLVED

**Resolution:** `CORSMiddleware` wired in `app/main.py`. Allow-list driven by `FRONTEND_ORIGIN` env var (CSV of absolute origins). When unset, falls back to `http://localhost:{3000,5173}` so local dev works out of the box. Set `FRONTEND_ORIGIN=https://<your-app>.lovable.dev` on Railway when frontend deploys.

---

## How to add an entry

Use the same structure: **What** / **Status** / **Why deferred** (or **Open**) / **Trigger to revisit** / **Implementation pointers**. Include the key files involved so future-you doesn't have to re-derive context.
