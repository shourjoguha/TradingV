# Backlog

Deferred decisions and known-but-unaddressed gaps. Each entry: what, why deferred, options considered, current state, trigger to revisit.

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

## Job submission queue (replace 5-min poll + eliminate 429s) — READY TO PICK UP

**What:** Today, manual `POST /v1/analysis/run` runs inline. Concurrent submissions get **429 `at_capacity`**, scheduled runs deferred by 429 wait up to **5 min** for the next poll (or fire early via `runner.request_wake()` from the in-flight job's completion hook). A real submission queue would accept every request, return `202 Accepted` immediately, and let a single worker drain in FIFO order.

**Status:** Deferred at v1. Hybrid (5-min poll + completion-trigger) ships today and is functionally adequate at current scale (~1 scheduled run/day + occasional manual). The full queue is well-scoped and **ready-to-pick-up** when usage friction surfaces.

**Trigger to revisit:**
- Operator hits 429 more than ~twice a week.
- Frontend UX needs "queued" status (rather than rejected → retry).
- Scheduled run keeps deferring beyond 30 min on a regular basis.
- Multiple watchlist groups want to run in sequence.

### Tier 1 — in-process async queue with DB persistence (~3–4 hr)

Minimal solution. No new infra.

- **New table** `submit_queue(id PK, inputs_json, enqueued_at, started_at, finished_at, job_id_fk, status)`. Migration adds it.
- **`POST /v1/analysis/run`** changes: insert `submit_queue` row, return `202 Accepted` with `{queue_id, status: 'queued'}`. No more 429.
- **New worker coroutine** in `app/main.py` lifespan: pulls oldest `pending` queue row, calls existing `_process_job`, writes `job_id` back, marks `done`, repeats. Single-flight (one queue row in flight at a time on laptop).
- **New routes**:
  - `GET /v1/analysis/queue` — list (visibility)
  - `GET /v1/analysis/queue/{queue_id}` — status (frontend polls this until `job_id` populates, then switches to polling `/v1/analysis/jobs/{job_id}`)
- **Schedule runner**: drops 5-min poll. Just enqueues like any caller. Removes pending_run/retry_minutes plumbing (but leave columns for back-compat).
- **Completion-trigger**: removed (worker auto-pulls next item).
- **Crash safety**: queue is in DB, surviving process restarts. On boot, worker resumes from oldest `pending`.

Trade-offs:
- ✅ No new infra; pure code change.
- ✅ Removes 429 entirely; removes 5-min latency.
- ✅ DB-durable.
- ❌ Still single-flight per backend (Kronos is CPU-heavy; multi-worker on free Railway = OOM).
- ❌ Queue is per-backend; laptop and Railway have separate queues — no global ordering.

### Tier 2 — Redis + arq workers (~1–2 days)

Production grade. Already flagged in `architecture.md` as the long-term plan.

- Railway Redis plugin (~$5/mo).
- `arq` library; worker process separate from web.
- Multiple worker concurrency (when GPU/parallel inference becomes possible).
- Built-in retries, dead-letter, priorities.
- Requires 2nd Railway service for the worker (or co-locate via process manager).

Use this only when Tier 1 falls over or when ML parallelism matters.

### Implementation pointers (Tier 1)

- Existing concurrency gate (`app/analysis/concurrency.py`) becomes redundant when the queue worker is single-flight — but leave it as belt-and-braces; cheap insurance against bugs in the worker.
- `_process_job` already has all the right hooks (post-job sync enqueue + `runner.request_wake()`); reuse without changes.
- Schedule runner: replace its `submit_run` call with `enqueue_submission(...)`. Remove the AtCapacityError branch.
- Frontend impact: change "Run now" handler from `expect 200/429` to `expect 202, then poll`. Small refactor.

---

## Trading-day filter per asset_class  ✅ RESOLVED

**Resolution:** Phase C2. `app/market_data/calendar.py::is_trading_day(asset_class, date)`: stocks/ETFs/forex/futures = Mon-Fri; crypto/commodity = always; unknown = always (permissive fallback). Scheduler partitions watchlist by asset class on each tick. Tested in `tests/test_calendar.py`.

---

## CORS middleware for browser-side Railway toggle  ✅ RESOLVED

**Resolution:** `CORSMiddleware` wired in `app/main.py`. Allow-list driven by `FRONTEND_ORIGIN` env var (CSV of absolute origins). When unset, falls back to `http://localhost:{3000,5173}` so local dev works out of the box. Set `FRONTEND_ORIGIN=https://<your-app>.lovable.dev` on Railway when frontend deploys.

---

## How to add an entry

Use the same structure: **What** / **Status** / **Why deferred** (or **Open**) / **Trigger to revisit** / **Implementation pointers**. Include the key files involved so future-you doesn't have to re-derive context.
