# Active tech debt

Things we know about, deferred on purpose, with the trigger to revisit. Different from [backlog.md](backlog.md): backlog tracks _features_ deferred for product reasons; tech_debt tracks _code cruft_ deferred for engineering reasons. When in doubt: if removing it would feel like a feature, it's backlog. If removing it would feel like a chore, it's here.

> **Review cadence:** monthly. Walk every entry — has its trigger fired? If yes, schedule the cleanup. Once this file crosses ~10 active entries, archive RESOLVED ones to `.claude/tech_debt-archive.md` to keep the active list scannable. Update the entry the moment a phase ships and intentionally leaves cruft behind — a stale tech_debt list is worse than none.

---

## `submit_queue` schedule_config columns (post-Phase queue)

**What:** `schedule_config.pending_run` and `schedule_config.retry_minutes` columns are unused after the job submission queue ships. The `last_run_status='deferred_429'` enum value becomes unreachable (queue can't 429).

**Why deferred:** Migration 0017 already creates the queue table; adding column-drop migrations is more rollback risk than the cruft is worth. Rows continue to be written with `pending_run=false`, `retry_minutes=<default>` — harmless.

**How to apply when ready:**
- New migration to `ALTER TABLE schedule_config DROP COLUMN pending_run, DROP COLUMN retry_minutes`.
- Remove read/write of those fields in `app/schedule/service.py` + `app/schedule/runner.py`.
- Remove "deferred_429" branch from any frontend page that surfaces `last_run_status`.

**Trigger to revisit:** another schedule_config schema change comes up — bundle this in.

---

## `app.analysis.concurrency` slot gate (post-Phase queue)

**What:** `app/analysis/concurrency.py` (`AtCapacityError`, `acquire_slot`) is kept inside `analysis.service.submit_run` after the queue ships. Belt-and-braces: queue worker is single-flight, so the slot gate should never fire. If it does, something's wrong upstream.

**Why deferred:** Cheap insurance. Removing it now means trusting the queue serialization completely; we want a few weeks of clean operation before that.

**How to apply when ready:**
- Delete `app/analysis/concurrency.py`.
- Remove `async with concurrency.acquire_slot()` in `app/analysis/service.py::submit_run`.
- Remove imports + the `AtCapacityError` catch (already gone from routes).
- Tests: drop `tests/test_analysis_concurrency.py` if it exists.

**Trigger to revisit:** queue runs cleanly for 4 weeks with zero `acquire_slot` failures (grep logs). Or: when scale forces multi-worker (Tier 2 in [backlog.md](backlog.md)).

---

## Tier 2 queue (Redis + arq) — long-term replacement

**What:** Tier 1 queue (in-process, single worker, DB-durable) is fine while Kronos is CPU-bound on a single core. When parallelism becomes possible (GPU lands or multi-process worker is desired), swap to Tier 2.

**Why deferred:** Premature for a single-user app with ~1 job/day.

**How to apply when ready:** see [backlog.md](backlog.md) "Job submission queue" → Tier 2 section. Adds a Redis dep + a separate worker process on Railway.

**Trigger to revisit:** sustained queue depth > 5 OR GPU inference lands OR Kronos-base CPU latency drops below 3s/run (parallelism becomes worth the infra).

---

## How to add an entry

Use this skeleton:

```markdown
## <short label> (<context>)

**What:** the cruft, one sentence.
**Why deferred:** the engineering reason.
**How to apply when ready:** concrete steps.
**Trigger to revisit:** the observable signal that says "now's the time."
```

If the entry has a feature angle, link to its [backlog.md](backlog.md) entry instead of duplicating.
