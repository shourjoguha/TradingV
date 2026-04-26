# Sync

Replication to a peer backend (dual-backend topology: laptop + Railway). After a job finishes, the running backend pushes:
1. The **tickers** it touched (so both DBs keep a historic catalog).
2. A **full job snapshot** (job + tasks + forecasts) — so prediction history is mirrored on both DBs regardless of which backend ran it.

OHLCV is NOT synced — each backend refetches live.

## Topology

```
┌─────────────┐   /v1/tickers      ┌─────────────┐
│   Laptop    │ ─────push─────────▶│   Railway   │
│ (primary)   │                    │ (replica)   │
│  pg:5439    │◀────push───────────│  pg:auto    │
│  :8000      │                    │  webhook in │
└─────────────┘                    └─────────────┘
     MAX_CONCURRENT_JOBS=1 each
```

- Laptop runs inference by default. Railway stays idle, receives TV webhooks.
- Frontend toggles backend per job. The non-running backend receives tickers after completion.
- Network: laptop is reachable from Railway via Tailscale (userspace networking + HTTP CONNECT proxy on `localhost:1055` inside the Railway container). Outbound httpx calls auto-route through `HTTP_PROXY` env var set by `tailscale-entrypoint.sh`. See [railway-deployment.md](railway-deployment.md) for the network model + setup.

## Outbox pattern

Durable queue with five row kinds. Each external write enqueues a row:
- `kind='ticker'` — one per (symbol, asset_class) when an analysis job finishes.
- `kind='result'` — one full job snapshot per finished analysis job.
- `kind='watchlist'` — one per watchlist add / update / delete.
- `kind='schedule'` — one per `PUT /v1/schedule` (full config snapshot).
- `kind='label'` — one per ticker-label upsert / delete.

A fire-and-forget `drain_outbox()` runs after each job + once on startup + on manual trigger. Drain dispatches by `kind` to the matching `peer_client.push_*` function. Same exponential-backoff retry policy applies to all kinds.

### Schema
```
sync_outbox(id, peer_url, kind, symbol, asset_class, payload_json,
            attempts, last_error,
            next_retry_at, created_at, completed_at)
```
- `kind`: `ticker | result | watchlist | schedule | label`. Default `ticker` (back-compat).
- `symbol`/`asset_class`: populated for `ticker` kind, NULL otherwise.
- `payload_json`: populated for everything except `ticker`. Carries the diff/snapshot.

Index: `(completed_at, next_retry_at)` — drain scan uses both.

### Retry policy
Exponential backoff: `30s × 2^(attempts-1)`, capped at 1h. On success: `completed_at=now, last_error=None`. On failure: `attempts+=1, next_retry_at=backoff(attempts), last_error=msg`.

### Peer receive
- **ticker rows** → peer `POST /v1/tickers`. Payload `{symbol, asset_class}`.
- **result rows** → peer `POST /v1/analysis/import`. Payload `{schema_version, origin, job, tasks}`. Idempotent on `job.id`.
- **watchlist rows** → peer `POST /v1/watchlist/import`. Payload `{action: upsert|delete, symbol, notes?, added_at?}`. Idempotent.
- **schedule rows** → peer `POST /v1/schedule/import`. Payload is the config-only snapshot (no runtime fields). Receiver preserves its own runtime fields (`pending_run`, `last_run_*`, `next_run_at`).
- **label rows** → peer `POST /v1/labels/import`. Payload `{action: upsert|delete, symbol, key, value?}`. Idempotent on (symbol, key).

### Loop avoidance
Each receiver writes directly to its DB **without going through the service-level enqueue path**, so importing a peer's change does NOT re-emit a sync row.

For analysis jobs: imported jobs are tagged `origin='peer'`; the post-job replication hook only fires for `origin='self'`. Prevents A→B→A bounce.

For watchlist/schedule/label: the `apply_imported_*` service helpers bypass the enqueue call entirely.

## Routes (`/v1/sync/*`)

- `POST /v1/sync/retry` — drains eligible rows now. Returns `{scanned, ok, failed}`.
- `GET /v1/sync/outbox?status=pending|completed|failed&limit=200` — visibility.

## Config

Peer push is skipped when `PEER_API_URL` or `PEER_API_KEY` is empty (`peer_configured()`). Set both on each backend pointing at its counterpart.

| Env | Purpose |
|---|---|
| `INSTANCE_NAME` | "laptop" or "railway" — for logs |
| `PEER_API_URL` | Base URL of the other backend |
| `PEER_API_KEY` | API key of the other backend (not this one) |
| `MAX_CONCURRENT_JOBS` | Concurrency gate (default 1) |

## Concurrency gate

`app/analysis/concurrency.py` owns an `asyncio.Lock + counter` (not `Semaphore` — TOCTOU-safe). `submit_run` acquires a slot BEFORE any DB writes; on contention raises `AtCapacityError` → route returns **429 `{"detail": "at_capacity"}`**. Prevents orphan job rows on rejection.

## Direction stance — both ways live

- **Laptop → Railway**: drains against Railway's public URL.
- **Railway → Laptop**: drains via Tailscale (userspace networking + HTTP CONNECT proxy on container :1055). Set up per [railway-deployment.md](railway-deployment.md).

Either backend can run a job and the other side will hold an `origin='peer'` copy with the same forecast.

## Known gaps
- No cleanup of completed rows (see [backlog.md](backlog.md) — sync_outbox cleanup task).
- `asset_class="unknown"` on peer upsert is not reconciled later if source backend learns the real class (see [backlog.md](backlog.md)).
