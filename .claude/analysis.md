# Analysis

Orchestrates Kronos inference over (ticker × interval × model) fan-out. Every submitted request creates a durable parent job and one task per cell. Ineligible cells resolve immediately with structured reasons — never silently dropped.

## Flow

`POST /v1/analysis/run` is now an enqueue: returns **202 Accepted** with `{queue_id, status: 'queued'}`. The single-flight queue worker (lifespan task) calls `submit_run()` to do the actual fan-out below. Frontend polls `/v1/analysis/queue/{queue_id}` until terminal, then jumps to `/v1/analysis/jobs/{job_id}`. See [queue.md](queue.md).

`POST /v1/analysis/run` body:
```json
{
  "tickers": ["AAPL", "BTC-USD"],
  "intervals": ["1d", "5m"],
  "model_ids": ["kronos_base"],      // optional; null = all registered
  "horizon_bars": 30                  // optional
}
```

1. Upsert every ticker (source `analysis`) — idempotent; persists for future dropdowns.
2. Fan out to tasks = tickers × intervals × model_ids.
3. For each task: count cached OHLCV bars for `(ticker, interval)`. If below the model's `min_history_bars` (cold start — typical on the first run for a new interval such as `1h`), trigger **one** lazy `md_service.refresh()` to warm the cache, then re-count. Self-healing — eliminates the chicken-and-egg case where the schedule runner used to refresh OHLCV only *after* predictions completed. One attempt only, so a permanently-unavailable combo doesn't repeatedly hammer the upstream provider.
4. `EligibilityValidator.check(...)` runs against the (possibly refreshed) bar count. Ineligible → `status="ineligible"`, populates `ineligible_reason` + `ineligible_message`. Eligible → `adapter.predict(...)`.
5. On task done → `predictions.service.explode_task` materialises `result_json.forecast[]` into `prediction_points` rows (best-effort, won't roll back the task).
6. Parent `status="done"` once every task resolves.

Returns `{job_id, task_count, status}` immediately. Poll `GET /v1/analysis/jobs/{id}` for state + partial results (response includes `origin`).

## Job origin tagging

Every `analysis_jobs` row carries `origin`:
- `'self'` (default) — created by THIS backend's `submit_run`.
- `'peer'` — inserted by `POST /v1/analysis/import` from the peer's outbox push.

Only `origin='self'` jobs trigger downstream sync (loop avoidance — see [sync.md](sync.md)).

## Concurrency gate (belt-and-braces, post-queue)

`submit_run` is wrapped in `concurrency.acquire_slot()` (lock + counter, `MAX_CONCURRENT_JOBS`-bounded). Under the Tier-1 queue this gate is functionally redundant — the worker is single-flight, so two `submit_run` calls never overlap from the route surface. Kept as defence-in-depth: if a future code path ever calls `submit_run` outside the worker (e.g. a script), the gate prevents corruption. Tracked in [tech_debt.md](tech_debt.md) for cleanup once the queue runs cleanly long enough.

## Post-job hooks

After the parent transitions to `done`, `_process_job`:
1. Collects `(symbol, asset_class)` pairs and serialises a full job snapshot.
2. Calls `sync_service.enqueue(...)` (ticker rows) + `enqueue_result(snapshot)` (one result row) + fires `drain_outbox()` as a background task. No-op if `PEER_API_URL`/`PEER_API_KEY` unset.
3. Fires `schedule.runner.request_wake()` — historically nudged a 429-deferred daily run. Under the queue this is no longer needed (worker auto-pulls the next item) but the call is harmless and kept for the rare external-caller case. See [schedule.md](schedule.md) and [tech_debt.md](tech_debt.md).

Both hooks skipped for `origin='peer'` jobs (loop avoidance).

## Operator cleanup (`POST /v1/analysis/jobs/{id}/abort`)

Force a stuck job to terminal state. Flips any `pending` / `running` tasks to `status='error'` with `"aborted: container restarted mid-run"` in the error message; sets the job to `done`. Already-`done` tasks are preserved as-is. Idempotent. Use only when a Railway redeploy killed the process mid-Kronos and left orphan `running` rows.

## Peer import (`POST /v1/analysis/import`)

Idempotent receiver for snapshots pushed from the peer. Schema:
```json
{
  "schema_version": 1,
  "origin": "<INSTANCE_NAME of sender>",
  "job":   {id, status, inputs_json, task_count, submitted_at, finished_at},
  "tasks": [{id, ticker, interval, model_id, status, result_json, started_at, finished_at, ...}, ...]
}
```
- Duplicate `job.id` → returns 200 `{"status": "duplicate"}` without re-inserting.
- New job → inserts tagged `origin='peer'`, then auto-explodes each task's forecast into `prediction_points` (same code path as live runs).
- Bad schema_version / missing job_id → 400.

## Tables

- `analysis_jobs(id UUID pk, status, inputs_json, task_count, origin, submitted_at, finished_at)` — `origin` is `'self' | 'peer'`.
- `analysis_tasks(id UUID pk, job_id fk CASCADE, ticker, interval, model_id, status, result_json, ineligible_reason, ineligible_message, error, started_at, finished_at)`.

Task status values: `pending | running | done | ineligible | error`.

`prediction_points` is materialised from `analysis_tasks.result_json` — see [predictions.md](predictions.md).

## Dispatch model
v1 processes tasks inline in the request handler (synchronous async). Fine while job rate is low. Once daily-scheduled runs across 40 tickers × multiple intervals start saturating, swap the loop for an `arq` worker on Redis — the validator + persistence shape stays identical; only dispatch changes.

## DEBUG_STUB
`SETTINGS.DEBUG_STUB=true` makes `StubAdapter.predict` return a deterministic synthetic forecast instead of raising. Use locally to exercise the orchestrator end-to-end. NEVER enable in production.

## Request-time vs task-time validation
- Request-time (400): non-canonical intervals, unknown `model_ids`, empty tickers. Rejects the whole submission.
- Task-time (200 + `ineligible`): canonical-but-unsupported intervals, asset-class mismatch, insufficient history, missing features, horizon out of range. Each cell resolves individually so partial failure is visible.
