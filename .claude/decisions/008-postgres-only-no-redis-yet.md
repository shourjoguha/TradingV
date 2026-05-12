# ADR-008: Postgres for everything durable; no Redis yet

**Date**: ongoing (since project inception); reaffirmed 2026-04-27 with queue Tier-1 choice
**Status**: Accepted

## Context

Modern web apps frequently split storage: Postgres for relational durability, Redis for queues + ephemeral caches. We chose to skip Redis from day one and use Postgres for everything.

## Options considered

- **A · Postgres for everything** — schema-managed durable state, queue, cache.
- **B · Postgres + Redis** — Redis for `submit_queue`, `sync_outbox`, hot OHLCV bars, rate-limit counters.
- **C · Different storage entirely (DynamoDB, etcd, file-system queues)** — not seriously considered.

## Decision

**Postgres for everything durable.** Including: alerts, tickers, OHLCV cache, analysis jobs/tasks, prediction_points, prediction_accuracy, drift_alerts, opportunities, trades, ticker_market_data, sync_outbox, schedule_config, watchlist, ticker_labels, submit_queue. Redis is reserved for the future.

Rationale:
- One storage primitive = one set of operational concerns. No "is the queue down?" debugging.
- Postgres is fast enough at this scale (single user, ~1 job/day, low row counts).
- Trivially debuggable: every state is `psql`-able + Alembic-managed.
- Free tier on Railway covers it without a second plugin.

## Trade-offs we accept

- Queue throughput is bounded by Postgres write speed (fine at single-flight).
- No native pub/sub (we use lifespan loops instead).
- Hot caches like "last price" would benefit from in-memory Redis; we don't have any yet.

## Trigger to revisit (→ adopt Redis)

- Sustained queue depth > 5 OR table grows past ~1M rows on the write path.
- Need for sub-100ms cache reads (e.g. real-time dashboard).
- Want to share state across multiple processes (currently inline lifespan tasks suffice).
- See [tech_debt.md](../status/tech_debt.md) "Tier 2 queue (Redis + arq)" for the upgrade path.

## Files affected

- `requirements.txt` — no Redis client.
- `app/main.py` — no Redis init.
- All modules use `app.core.db.SessionLocal` for state.

## Cross-references

- [architecture.md](../guides/architecture.md) — "Storage split" section
- [tech_debt.md](../status/tech_debt.md) — Tier-2 queue deferral
