# Submit queue (Tier 1)

In-process FIFO drain for analysis-job submissions. Replaces the previous 429-on-busy + 5-min-poll-recovery pattern. See [.claude/tech_debt.md](../status/tech_debt.md) for deferred decisions (concurrency slot gate kept as belt-and-braces; Tier-2 Redis-arq reserved for when Kronos parallelism matters).

## Schema

```
submit_queue(
  id PK,
  inputs_json JSON,           -- AnalysisRunRequest payload
  status ENUM('pending'|'running'|'done'|'failed'|'cancelled') DEFAULT 'pending',
  source ENUM('manual'|'schedule'|'fallback') DEFAULT 'manual',
  enqueued_at, started_at, finished_at,
  job_id FK NULLABLE → analysis_jobs (SET NULL),
  error TEXT NULLABLE
)
```

Indexes: `(status, enqueued_at)` for the worker's "next pending" pull; `(enqueued_at)` for list views.

## Lifecycle

```
pending → running → done | failed
                  (or)  → cancelled (only allowed from pending)
```

`UNIQUE` not enforced on `(inputs_json, source)` — duplicate manual submits are accepted; user can cancel one before it runs.

## Worker

`app/queue/worker.py::worker_loop()` — single coroutine wrapped in the lifespan task list.

- Polls every 5s OR wakes immediately on `request_wake()` (called by `enqueue` + scheduler).
- Claim phase: `claim_next()` uses `FOR UPDATE SKIP LOCKED` on Postgres (serial SELECT-then-UPDATE on SQLite for tests).
- Run phase: outside the claim transaction, calls `analysis.service.submit_run(**inputs_json)` → marks `done` with `job_id`, OR `failed` with `error`.
- Cancellation-safe: caught `CancelledError` re-raised cleanly; the partially-running row stays `running` and gets reverted to `pending` on next boot via `reset_stuck_on_boot()`.

## Crash recovery

`app/queue/service.py::reset_stuck_on_boot()` — called once at lifespan startup. `UPDATE submit_queue SET status='pending', started_at=NULL WHERE status='running'`. Logs a warning per row. The downstream `analysis_jobs` row has its own UUID, so re-running a recovered queue item only risks producing a duplicate analysis_job — never data corruption.

## Endpoints (`/v1/analysis/queue/*`)

```
GET    /v1/analysis/queue                 list (?status=, ?limit=)
GET    /v1/analysis/queue/stats           counts by status — powers Dashboard widget
GET    /v1/analysis/queue/{id}            single-item poll (frontend uses for toast lifecycle)
POST   /v1/analysis/queue                 manual enqueue (rare; main path is /v1/analysis/run)
DELETE /v1/analysis/queue/{id}            cancel pending → 200 / 409 if running / 404 if missing
```

`POST /v1/analysis/run` is now a thin wrapper:
1. Pre-validate inputs (`service.validate_inputs`) → 400 on bad input.
2. `queue.enqueue(...)` → returns `{queue_id, status: 'queued'}` with HTTP **202**.

Frontend polls `GET /v1/analysis/queue/{id}` until `status in {done, failed, cancelled}`, then jumps to `/v1/analysis/jobs/{job_id}`.

## Schedule integration

`app/schedule/runner.py::_tick` and `_fallback_tick` both call `queue.enqueue(source='schedule'|'fallback')` instead of `analysis.submit_run`. The 429-deferred path (`pending_run`, `retry_minutes`, `last_run_status='deferred_429'`) is unreachable under the queue — see [tech_debt.md](../status/tech_debt.md) for the column-cleanup trigger.

## Frontend

- `useQueue({ status, limit })` — list, polls every 5s.
- `useQueueStats()` — counts for Dashboard widget.
- `useQueueItem(id)` — single-item poll, auto-stops on terminal status.
- `useCancelQueueItem()` — DELETE mutation.
- `useRunAnalysis()` — returns `{queue_id}`; `onSuccess` toast: `"Queued: <id>"`.

UI surfaces:
- **Dashboard `QueueWidget`**: shown only when pending+running > 0. Pending count, running count, current ticker, FIFO peek list.
- **AnalysisJobs `Queue` card**: above Job History. Lists running + pending items; cancel button on pending only.

## Files

- `migrations/versions/0017_submit_queue.py`
- `app/queue/{__init__,models,service,worker,routes}.py`
- `app/main.py` lifespan: `reset_stuck_on_boot()` + `worker_loop` task
- `app/api/router.py`: queue routes registered
- `app/analysis/routes.py`: `/run` becomes thin wrapper
- `app/analysis/service.py`: extracted `validate_inputs()` helper
- `tests/test_queue.py` — 22 tests (service unit, worker integration, route)
