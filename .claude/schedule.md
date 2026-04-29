# Schedule

Daily forecast scheduler. Single config row → in-process async runner.

## Schema (singleton row, id=1)
```
schedule_config(
  id, enabled, tz_name, run_at_local, intervals, horizon_bars,
  model_ids, retry_minutes, collect_actuals, skip_weekends, pending_run,
  last_run_at, last_run_status, last_run_error, next_run_at, updated_at
)
```

## Defaults (locked v1)
- `enabled=False` — opt-in via PUT
- `tz_name='UTC'`
- `run_at_local=23:30`
- `intervals=['1d']`
- `horizon_bars=5`
- `model_ids=['kronos_base']`
- `retry_minutes=5`
- `collect_actuals=True`
- `skip_weekends=True`

## Routes
- `GET  /v1/schedule` → current config + last-run status
- `PUT  /v1/schedule` → partial update (any subset of fields). Bad `tz_name` → 400.
- `POST /v1/schedule/fire-now` → set `pending_run=true` and wake the runner.

## Runner (`app/schedule/runner.py`)
Started in `app.main` lifespan. Single async loop:

1. `is_due(cfg)` — true if `enabled` AND (`pending_run` OR `now >= next_run_at`).
2. Tick:
   - Skip if today is Sat/Sun AND `skip_weekends` → status `skipped_weekend`.
   - Skip if watchlist empty → status `skipped_empty`.
   - Else `submit_run(watchlist, intervals, model_ids, horizon_bars)`:
     - Success → `succeeded`, `pending_run=false`, advance `next_run_at`.
     - `AtCapacityError` → `deferred_429`, `pending_run=true`. Don't advance — retry every `retry_minutes`.
     - Other exception → `failed` + error msg, advance `next_run_at`.
3. Sleep until `min(next_run_at, retry_minutes_from_now if pending, idle_poll=30s)`. External callers wake the loop early via `runner.request_wake()`.

## Completion-trigger
At end of `_process_job` in `app/analysis/service.py`, `runner.request_wake()` is called. If a scheduled run was deferred by 429, this fires it as soon as the in-flight manual job finishes — no 5-minute wait.

## Actuals collection (Phase 4)
After `submit_run` succeeds, the runner refreshes OHLCV cache for every (watchlist symbol × interval) via `md_service.refresh`. Best-effort: per-symbol failures are logged but don't fail the scheduled run. Disabled by setting `collect_actuals=false` in `schedule_config`.

This is what makes the comparison endpoints (Phase 5) meaningful — actuals for past target dates are guaranteed to be in `ohlcv_bars` shortly after each run.

Right after `_collect_actuals`, the runner also calls `accuracy.service.evaluate_pending()` (best-effort, log-and-swallow). This pairs newly-cached actuals with elapsed predictions immediately, so the Accuracy tab reflects last night's run by morning rather than waiting up to 1h for the hourly `evaluator_loop` tick.

## Catch-up at startup
First-iteration of the loop computes `next_run_at` if missing. If it's already in the past (laptop was off through the scheduled time), the loop fires immediately on startup.

## Sync to Railway
Schedule config replicates to peer via outbox (`kind='schedule'`) on every PUT — see [sync.md](sync.md). Receiver preserves runtime-only fields (`pending_run`, `last_run_*`, `next_run_at`).

## Railway-fallback inference (opt-in)

If the laptop fails to push today's predictions, Railway runs them itself. Off by default; enable on Railway with `RAILWAY_FALLBACK_ENABLED=true` env var (set + redeploy).

How it works:
- `start()` spawns a second asyncio task `_fallback_loop()` only when `INSTANCE_NAME='railway'` AND `RAILWAY_FALLBACK_ENABLED=true`.
- Loop ticks every 30 min. Each tick:
  - Compute deadline = most-recent-past `run_at_local` instant + `fallback_offset_hours` (default 6h, configurable on `schedule_config`).
  - If `now < deadline`: skip (still within the laptop's window).
  - Else, scan watchlist symbols. For each, check `prediction_points` for any row with `made_on >= candidate_run.date()`.
    - Already populated → skip ticker (laptop got there first, OR a prior fallback tick covered it).
    - Missing → include in the fallback fire list.
  - If fire list non-empty → call `submit_run(...)` on Railway with that subset.

Edge cases:
- If laptop comes online AFTER Railway's fallback fires: laptop's run will produce a duplicate. Per-day dedupe is best-effort — accepted v1 limitation. Frontend can filter by `origin` for clarity.
- If `enabled=false` on schedule_config: fallback also skipped (config gates everything).
- `fallback_offset_hours` is configurable per backend; tune if 6h is too tight for a slow laptop boot or too loose for an outage response.
