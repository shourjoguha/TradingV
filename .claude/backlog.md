# Backlog

Deferred decisions and known-but-unaddressed gaps. Each entry: what, why deferred, options considered, current state, trigger to revisit.

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
