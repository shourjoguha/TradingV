# ADR-003: Tier-1 in-process queue over Tier-2 (Redis + arq)

**Date**: 2026-04-27
**Status**: Accepted

## Context

`POST /v1/analysis/run` was inline + 429 on busy. Scheduled runs deferred up to 5 min on 429. Operator-felt friction: occasional 429 toasts; frontend had to handle two response shapes; scheduled runs sometimes deferred unnecessarily. Backlog had this as READY-TO-PICK-UP with a clear Tier-1 vs Tier-2 spec.

## Options considered

- **A · Tier 1 — in-process queue, single worker, Postgres-backed** — `submit_queue` table, `worker_loop()` lifespan task, ~3-4h to ship.
- **B · Tier 2 — Redis + arq workers** — separate worker process on Railway, multi-concurrency, retries, dead-letter, priorities. ~1-2 days + Redis plugin.
- **C · Status quo** — leave as-is.

## Decision

**Tier 1.** Reasons:
- Single user, ~1 scheduled run/day + occasional manual; no need for multi-worker concurrency.
- Kronos is CPU-heavy; multi-worker on Railway free tier would OOM.
- Tier 2 is well-scoped → easy upgrade path when scale forces it.
- DB-durable, no new infra dependencies.

Trade-offs accepted:
- ❌ Single-flight per backend (laptop and Railway have separate queues; no global ordering).
- ❌ Worker lives in the same Python process as the web → if lifespan dies, queue dies (manual restart needed).
- ✅ Removes 429 entirely; removes 5-min latency.
- ✅ Crash safety via `reset_stuck_on_boot`.

## Trigger to revisit (→ Tier 2)

- Sustained queue depth > 5 (not transient bursts).
- GPU inference lands and parallel processing becomes possible without OOM.
- Multiple watchlist groups want to run in sequence with priority weighting.

## Files affected

- `migrations/versions/0017_submit_queue.py`
- `app/queue/{__init__,models,service,worker,routes}.py`
- `app/main.py` (lifespan, `reset_stuck_on_boot` + `worker_loop`)
- `app/api/router.py` (queue routes)
- `app/analysis/routes.py` (`/run` becomes thin wrapper)
- `app/analysis/service.py` (extracted `validate_inputs()`)
- `app/schedule/runner.py` (replaced `submit_run` with `queue.enqueue`)
- `frontend/src/{lib/types,hooks/use-api,pages/Dashboard,pages/AnalysisJobs}.tsx`
- `tests/test_queue.py` (22 new tests)

## Cross-references

- [queue.md](../modules/queue.md) — full queue contract
- [tech_debt.md](../status/tech_debt.md) — Tier-2 deferral entry
- [backlog.md](../status/backlog.md) — "Job submission queue" RESOLVED
