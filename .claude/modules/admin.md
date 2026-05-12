# admin

Loop registry + `app_settings` cascade + `process_status` writes + Anthropic
kill-switch / monthly cap. Backs the tabbed `/admin/:tab?` UI shipped in
Phase 3 of the cost-aware iteration (see
`.claude/plans/ok-now-we-have-distributed-anchor.md`).

## Tables

| Table | Purpose |
|---|---|
| `app_settings` | `key TEXT PK, value_json JSONB, updated_at`. Cascade: DB > env > hardcoded default. |
| `process_status` | One row per registered lifespan loop. `last_tick_at`, `last_tick_ok`, `last_error` (1000 chars max), `last_error_at`, `last_duration_ms`, `updated_at`. |

Both tables are per-instance state. Neither replicates via the sync outbox.
Migration `0025_admin_settings_and_process_status.py`.

## Files

| File | Purpose |
|---|---|
| `loops.py` | Static `LOOPS: dict[str, LoopMeta]` registry. Single source of truth for the Admin UI. Every loop spawned in `app.main:lifespan` MUST have a row. |
| `runtime.py` | In-process `LoopHandle` registry. Lifespan startup populates it; routes mutate it (manual fire, abort). Cleared on process restart. |
| `service.py` | Settings cascade (`get_setting` / `set_setting`), `record_tick`, cost guards (`anthropic_kill_switch_active`, `month_to_date_anthropic_spend_usd`). |
| `lifespan.py` | `register_handle()`, `tick_status()` async-context-manager, `assert_registry_drift()`. |
| `routes.py` | `/v1/admin/loops`, `/v1/admin/loops/{id}/{fire,abort,cadence}`, `/v1/admin/settings`. |

## Settings cascade

`get_setting(key, default)` resolution order:

1. **DB row** in `app_settings` (most-recent operator value)
2. **Env var** (uppercased, dots → underscores; e.g. `anthropic.enabled` → `ANTHROPIC_ENABLED`). Coerced to the type of the hardcoded default.
3. **Hardcoded default** in `_HARDCODED_DEFAULTS` (e.g. `anthropic.enabled = True`)
4. **Caller-supplied default** if none of the above match

Validate-at-read: every loop calls `get_setting(...)` on each tick; operator
edits propagate without restart. No caching beyond Postgres' own.

## Cost guards (C1–C6)

| Guard | Setting | Effect |
|---|---|---|
| C1 | `research_weekly.enabled` | Default `False`. Operator opts in. Default cadence is **monthly**. |
| C2 | `research_weekly.scope` | `at_risk` (default) or `all`. Filters via existing `app/research/weekly.py:_rank_active`. |
| C3 | `anthropic.enabled` | Master kill-switch. False → Research + TV vision return 503-style synthetic error. |
| C4 | `anthropic.monthly_cap_usd` | Default `5.00`. `anthropic_kill_switch_active()` flips True when month-to-date spend ≥ cap. |
| C5 | `tv_context.vision_enabled_this_month` | Independent monthly toggle for the vision call (operator can disable vision while keeping research on). |
| C6 | Manual fire is the primary path | Default-off where Anthropic spend is involved. Schedule loops still run unattended. |

C3 + C4 short-circuit Claude calls in `app/research/service.py:ask` and
`app/tv_context/vision.py:summarize_chart` before any tokens are charged.
The synthetic responses preserve the normal response shape so the UI
doesn't blow up — just shows a clear "kill-switch active" verdict.

## Endpoints

`GET /v1/admin/loops` — list every registered loop with metadata, current
status, and cadence. Auto-refreshed by the Processes tab every 30s.

`POST /v1/admin/loops/{id}/fire` — invoke the loop's manual-fire callable.
30s server-side debounce returns `429` with `retry_after_seconds` on rapid
re-fires. Loops without a `fire_now` callable return `400`.

`POST /v1/admin/loops/{id}/abort` — sets the loop's `stop_event` and
cancels its task. Only loops where `meta.supports_abort` is `True` accept
this.

`PUT /v1/admin/loops/{id}/cadence` — writes `loop.cadence.{id}` and (optional)
`loop.enabled.{id}` to `app_settings`. Next tick reads the new value.

`GET /v1/admin/settings` — returns the whitelist of editable cost guards
plus computed values (`anthropic.month_to_date_usd`,
`anthropic.kill_switch_active`).

`PUT /v1/admin/settings/{key}` — operator toggle for the whitelist. Random
keys return `400`.

## Tests

- `tests/test_admin_settings_cascade.py` — DB > env > default precedence; kill-switch via explicit disable + via cap breach.
- `tests/test_admin_loops.py` — list, fire (debounce → 429), abort, cadence update, status recording, settings whitelist enforcement.

## Costs + Retention (Phase 5)

`app/admin/costs.py` aggregates `est_cost_usd` across `research_queries` +
TV `vision.cost_usd` payloads. Three endpoints:

- `GET /v1/admin/costs/monthly?month=YYYY-MM` — totals + counts
- `GET /v1/admin/costs/recent?days=30` — daily series for the chart
- `GET /v1/admin/costs/top-queries?limit=10` — most expensive queries this month

In-process cache TTL: **5 minutes**. Cleared via `costs.clear_cache()` for
tests.

`app/admin/retention.py` ships per-class TTL config + sweep functions:

- `sweep_prediction_accuracy()` — `evaluated_at < today - 365d`
- `sweep_drift_alerts()` — `acknowledged_at < today - 90d` (unacked stay forever)
- `sweep_research_queries()` — per-status matrix: approved + pending forever, dismissed = 180d, error = 90d

Plus vault sweeps:
- `tools/vault_indexer/cleanup_filings.py:cleanup_old_8k()` — drops 8-K filings > 18 months
- `tools/the_street/consolidate.py:maybe_rollup_quarter()` — keeps last 13 weekly snapshots; older quarters consolidated into `<vault>/The Street/quarterlies/<YYYY-QN>/quarter-rollup.md` (rollup written BEFORE source deletion)

`run_full_sweep()` runs DB sweeps → vault sweeps → `POST :8001/reload` in order.

Retention tab UI: `GET /v1/admin/retention` returns row counts + oldest row
+ TTL per class. Manual purge is two-step (preview → confirm) and capped
at **5000 rows per click** (`MANUAL_PURGE_CAP`) to keep the DB-lock window
bounded.

## Future

- Phase 4 of the original IA-reorg plan (smart-money auto-pipeline) is
  still deferred. Several of its sources are now redundant with EDGAR
  direct ingest — see `.claude/plans/ok-now-we-have-distributed-anchor.md`.
- Steering events from `app/research/weekly.py` could write to
  `process_status.last_error` for diagnostic surfacing — currently they
  log to `<vault>/Research/_steering-log.md`.
- Phase 5 of the cost-aware iteration adds a `retention` loop that this
  registry will need to register.
