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

## sync_outbox cleanup task

**What:** `sync_outbox` table grows unbounded; completed rows never deleted.

**Status:** Open. No production impact yet (low row count).

**Trigger to revisit:** When row count exceeds ~10k or query latency on `ix_sync_outbox_pending` degrades.

**Implementation:** Add a periodic task (`asyncio.create_task` on startup) that deletes rows where `completed_at < now() - 7 days`.

---

## asset_class reconciliation

**What:** When sync pushes a ticker as `asset_class='unknown'` (because we hadn't classified it yet), and the source backend later learns the real class, the receiver isn't updated.

**Status:** Open. Cosmetic — doesn't affect inference correctness.

**Trigger to revisit:** When a downstream feature relies on accurate `asset_class` on both backends (e.g. cross-asset screening).

**Implementation:** Push a follow-up `kind='ticker'` row whenever `tickers_svc.upsert_ticker` upgrades the class. Or a periodic reconciliation drain.

---

## How to add an entry

Use the same structure: **What** / **Status** / **Why deferred** (or **Open**) / **Trigger to revisit** / **Implementation pointers**. Include the key files involved so future-you doesn't have to re-derive context.
