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
4. Parent `status="done"` once every task resolves.

Returns `{job_id, task_count, status}` immediately. Poll `GET /v1/analysis/jobs/{id}` for state + partial results.

## Concurrency gate (429)

`submit_run` is wrapped in `concurrency.acquire_slot()` (lock + counter, `MAX_CONCURRENT_JOBS`-bounded). If full, raises `AtCapacityError` → route returns **429 `{"detail": "at_capacity"}`**. Gate sits BEFORE DB writes so rejected requests leave no orphan rows. See [sync.md](sync.md).

## Peer sync hook

After the parent job is marked `done`, `_process_job` collects `(symbol, asset_class)` pairs and calls `sync_service.enqueue(...)` + fires `drain_outbox()` as a background task. No-op if `PEER_API_URL`/`PEER_API_KEY` unset. See [sync.md](sync.md).

## Tables

- `analysis_jobs(id UUID pk, status, inputs_json, task_count, submitted_at, finished_at)`
- `analysis_tasks(id UUID pk, job_id fk, ticker, interval, model_id, status, result_json, ineligible_reason, ineligible_message, error, started_at, finished_at)`

Task status values: `pending | running | done | ineligible | error`.

## Dispatch model
v1 processes tasks inline in the request handler (synchronous async). Fine while the Kronos stub is wired. Phase 5 swaps the loop for an `arq` worker on Railway Redis — the validator + persistence shape stays identical; only dispatch changes.

## DEBUG_STUB
`SETTINGS.DEBUG_STUB=true` makes `StubAdapter.predict` return a deterministic synthetic forecast instead of raising. Use locally to exercise the orchestrator end-to-end. NEVER enable in production.

## Request-time vs task-time validation
- Request-time (400): non-canonical intervals, unknown `model_ids`, empty tickers. Rejects the whole submission.
- Task-time (200 + `ineligible`): canonical-but-unsupported intervals, asset-class mismatch, insufficient history, missing features, horizon out of range. Each cell resolves individually so partial failure is visible.
