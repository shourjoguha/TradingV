# Sync

Ticker catalog replication to a peer backend (dual-backend topology: laptop + Railway). After a job finishes, the running backend pushes the tickers it touched to the peer so both DBs keep a historic ticker list. OHLCV is NOT synced — each backend refetches live.

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
- LAN-only for v1. Tunnel (Cloudflare/Tailscale) added when frontend ships.

## Outbox pattern

Durable queue. Completed analysis jobs enqueue one `sync_outbox` row per (symbol, asset_class). A fire-and-forget `drain_outbox()` runs after each job + once on startup + on manual trigger.

### Schema
```
sync_outbox(id, peer_url, symbol, asset_class,
            attempts, last_error,
            next_retry_at, created_at, completed_at)
```
Index: `(completed_at, next_retry_at)` — drain scan uses both.

### Retry policy
Exponential backoff: `30s × 2^(attempts-1)`, capped at 1h. On success: `completed_at=now, last_error=None`. On failure: `attempts+=1, next_retry_at=backoff(attempts), last_error=msg`.

### Peer receive
Peer upserts via existing `POST /v1/tickers` — reuses `tickers_svc.upsert_ticker`. Payload is `{symbol, asset_class}` only. Idempotent, so retries are safe.

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

## Known gaps
- No cleanup of completed rows (table grows unbounded — add a 7-day purge task later).
- No public tunnel yet — Railway → laptop pushes fail until user opens one; outbox retries cover the gap.
- `asset_class="unknown"` on peer upsert is not reconciled later if source backend learns the real class.
