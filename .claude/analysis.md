# Analysis

Orchestrates Kronos inference over (ticker × interval × model) fan-out. Every submitted request creates a durable parent job and one task per cell. Ineligible cells resolve immediately with structured reasons — never silently dropped.

## Flow

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
3. For each task: `EligibilityValidator.check(...)` against current OHLCV cache size. Ineligible → `status="ineligible"`, populates `ineligible_reason` + `ineligible_message`. Eligible → `adapter.predict(...)`.
4. On task done → `predictions.service.explode_task` materialises `result_json.forecast[]` into `prediction_points` rows (best-effort, won't roll back the task).
5. Parent `status="done"` once every task resolves.

Returns `{job_id, task_count, status}` immediately. Poll `GET /v1/analysis/jobs/{id}` for state + partial results (response includes `origin`).

## Job origin tagging

Every `analysis_jobs` row carries `origin`:
- `'self'` (default) — created by THIS backend's `submit_run`.
- `'peer'` — inserted by `POST /v1/analysis/import` from the peer's outbox push.

Only `origin='self'` jobs trigger downstream sync (loop avoidance — see [sync.md](sync.md)).

## Concurrency gate (429)

`submit_run` is wrapped in `concurrency.acquire_slot()` (lock + counter, `MAX_CONCURRENT_JOBS`-bounded). If full, raises `AtCapacityError` → route returns **429 `{"detail": "at_capacity"}`**. Gate sits BEFORE DB writes so rejected requests leave no orphan rows. By design — daily scheduler also respects this and defers via `pending_run` flag.

## Post-job hooks

After the parent transitions to `done`, `_process_job`:
1. Collects `(symbol, asset_class)` pairs and serialises a full job snapshot.
2. Calls `sync_service.enqueue(...)` (ticker rows) + `enqueue_result(snapshot)` (one result row) + fires `drain_outbox()` as a background task. No-op if `PEER_API_URL`/`PEER_API_KEY` unset.
3. Fires `schedule.runner.request_wake()` — in case a daily run was deferred by `AtCapacityError`, wakes the scheduler immediately. See [schedule.md](schedule.md).

Both hooks skipped for `origin='peer'` jobs (loop avoidance).

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
