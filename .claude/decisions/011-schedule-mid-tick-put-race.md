# ADR-011: Choke-point recompute of `next_run_at` (no `is_running` flag)

**Date**: 2026-04-30
**Status**: Accepted

## Context

The scheduler runner has two paths that can write `schedule_config.next_run_at`:

1. `update_config` (called from `PUT /v1/schedule`) — recomputes when `enabled`, `tz_name`, or `run_at_local` change.
2. `record_run` at the end of `_tick` — was given a precomputed `advance_to` value snapshotted at the **start** of the tick.

When a PUT lands during a tick (which can take seconds-to-minutes when an analysis fan-out is enqueued), both paths fire and the latter wins. Because `advance_to` was computed against the pre-PUT config, the operator's freshly-PUT config gets clobbered. Symptom from the field: an operator hot-edits `run_at_local` while a run is still firing, expects today's later slot to be honored, and instead finds `next_run_at` set to tomorrow against the old `run_at_local`.

The original backlog entry proposed adding an `is_running` flag and a deferred recompute path. That works but adds:
- A new column on the singleton config row.
- A new piece of state to keep consistent across crashes.
- Two write moments (during PUT, and at end of tick) that need to synchronise.

We considered something simpler.

## Decision

Move the **only** post-tick advancement into `record_run`, and have it recompute `next_run_at` against the **freshly-loaded** config row inside its own session.

- `_tick` no longer precomputes `next_after_run`. It computes a single `advance_now = now + 1 min` (the instant past the slot just fired) and passes that through.
- `record_run(*, advance_now=…)` opens a new session, loads `ScheduleConfig`, and calls `compute_next_run_at(cfg, now=advance_now)`. Whatever the operator did to `run_at_local` / `tz_name` / `skip_weekends` / `enabled` mid-tick is reflected in the computation.
- `update_config` keeps its own immediate recompute for PUTs that happen outside any tick (so the change is visible right away).

When a PUT and a tick overlap, the writes serialise like this:

```
T0    tick starts, reads cfg (run_at_local=21:30)
T1    operator PUTs run_at_local=23:30 → update_config writes next_run_at=23:30 today
T2    tick body finishes
T3    record_run reloads cfg (run_at_local=23:30) → recomputes against advance_now=21:31
      → next_run_at = today 23:30 (correct)
```

The PUT's write at T1 is overwritten at T3, but with the **same** correct value — so the operator sees their intent honored. No `is_running` flag needed; SQL-level row writes handle the ordering.

## Why this over the `is_running` flag

- One source of truth (`record_run`) for the advancement value.
- Fewer columns, fewer migrations, fewer crash-recovery cases.
- `record_run` was already serial with the runner — it already runs after the tick body, no new synchronisation primitive.
- The race is *eliminated* rather than *deferred*. The flag-based design still has a window between PUT-recompute and end-of-tick where the value is stale; choke-point design closes it.

## Trade-offs we accept

- A PUT that lands on an already-completed run still gets a follow-up overwrite from `record_run` IF the runner is in the middle of starting the next tick. In practice this is harmless — `record_run` recomputes from the fresh cfg, so the value is correct either way.
- Slightly more work inside `record_run` (an extra `compute_next_run_at`). Cost: a few microseconds, called once per tick.

## Trigger to revisit

- If we ever add a second writer of `next_run_at` (e.g. an alternate scheduler), revisit. The choke-point assumes `record_run` is the only end-of-tick writer.
- If runs become long-lived (>1 min) AND PUT cadence becomes high (multiple operators), surface a UI banner or status field that says "schedule change applied; will take effect after current run." Today the value is correct after the tick, but the operator can't tell from the UI that there was a brief overlap.

## Files affected

- `app/schedule/service.py::record_run` — accepts `advance_now`, recomputes inside the function.
- `app/schedule/runner.py::_tick` — passes `advance_now` instead of `advance_to`.
- `tests/test_schedule.py` — `test_record_run_uses_post_put_config`, `test_record_run_without_advance_leaves_next_run_at`.
- `.claude/schedule.md` — "Mid-tick PUT race — choke-point recompute" section.
- `.claude/backlog.md` — entry marked RESOLVED.

## Cross-references

- [schedule.md](../modules/schedule.md) — operational doc.
- [backlog.md](../status/backlog.md) — original bug entry.
