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

## Catch-up at startup
First-iteration of the loop computes `next_run_at` if missing. If it's already in the past (laptop was off through the scheduled time), the loop fires immediately on startup.

## Sync to Railway
Schedule config is laptop-only for v1 — see [backlog.md](backlog.md).
