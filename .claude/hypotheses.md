# Hypotheses

Operator-curated trading theses. Persistent, structured beliefs the platform
tracks daily and cascades through dependencies. **Load-bearing for M-3+** —
opportunities, the LLM research endpoint, and backtest replay all attach to
hypotheses to weight signals and ground answers.

Phase: M-2 (shipped 2026-05-01). Promoted from outline at
[plans/M-2-hypothesis-object.md](plans/M-2-hypothesis-object.md).

## Schema

```
hypothesis(
  id PK (uuid str), slug UNIQUE, title,
  claim_type (regime|tactical|single_name|breakout),
  axis (free-form taxonomy bucket, indexed with status),
  parent_id FK→hypothesis (sizing dependency, ON DELETE SET NULL),
  precondition_id FK→hypothesis (existence dependency, ON DELETE SET NULL),
  primary_metric, tracking_signal,
  invalidator JSON (DSL — see below),
  ttl_months INT (>0; expires_at = created_at + ttl_months × 30 days),
  created_at, expires_at,
  status (active|expired|invalidated|cancelled|manual_closed),
  body_md  -- full markdown body from the source draft
)

hypothesis_evaluation(
  id PK, hypothesis_id FK ON DELETE CASCADE,
  evaluated_at, status_before, status_after,
  reason TEXT, invalidator_result JSON
)
```

Indexes: `(status, axis)`, `(precondition_id)`, `(parent_id)`, `(expires_at)`,
`(hypothesis_id, evaluated_at DESC)`.

`JSON` (not `JSONB`) so SQLite test parity is free. Postgres can index later
if a query path warrants it.

## Invalidator DSL

Single shape: `{"op": "<name>", "args": {...}}`. Validators reject unknown
ops or malformed args at create / update time so `evaluate()` always trusts
the shape. See [app/hypotheses/invalidator.py](../app/hypotheses/invalidator.py).

| op | args | semantics |
|---|---|---|
| `ratio_below_sma` | `numerator, denominator, sma_days, days_below` | M-1 ratio < its `sma_days` SMA for `days_below` consecutive days. |
| `series_above_threshold` | `symbol, threshold, days_above` | Raw `MacroSeries` value > threshold for `days_above` consecutive days. |
| `series_below_threshold` | `symbol, threshold, days_below` | Mirror; `<` strict. |
| `series_change_pct` | `symbol, window_months, threshold_pct, direction (up\|down)` | `(latest − first) / first × 100` crosses threshold in `direction`. |
| `manual` | `{}` | Never auto-fires. Operator dismisses via `POST /cancel`. |

Each evaluation returns `InvalidatorResult { fired, observed, reason }`.
`observed` is the raw values inspected — persisted to
`hypothesis_evaluation.invalidator_result` for forensics.

## TTL defaults per claim_type

```
regime      → 30 months
breakout    → 30 months
tactical    →  6 months
single_name → 18 months
```

Snapshotted at create time. Operator override wins (drafts use this — e.g.
`btc-bottom-3m` is `regime` but `ttl_months=3`). See
[app/hypotheses/service.py](../app/hypotheses/service.py)
`TTL_BY_CLAIM_TYPE`.

## Daily lifespan tick

Runs every 24h from `app/main.py` lifespan. Three steps in order:

1. **TTL expiry** — `active` rows past `expires_at` flip to `expired`.
2. **Invalidator evaluation** — DSL runs against current macro data; `fired`
   → `invalidated`.
3. **Cascade** — `active` rows whose `precondition_id` row is no longer
   `active` flip to `cancelled`. Recursive (bounded at 10 iterations to
   guard against circular precondition graphs).

Every transition writes a `hypothesis_evaluation` row with `reason` +
optional `invalidator_result`. Force-fire for testing or operator audit
via `POST /v1/hypotheses/_tick` (tick is API-key-gated, no separate auth).

First tick deferred 5 minutes after boot so macro ingestion gets a head
start on day 0.

## Routes

```
GET    /v1/hypotheses?status=&axis=&claim_type=   list (filterable)
GET    /v1/hypotheses/summary                     {active,expired,...,at_risk}
GET    /v1/hypotheses/{id}                        + recent_evaluations[10]
POST   /v1/hypotheses                             create
PATCH  /v1/hypotheses/{id}                        partial update
DELETE /v1/hypotheses/{id}                        cascades evaluations
POST   /v1/hypotheses/{id}/cancel                 manual close (records evaluation)
POST   /v1/hypotheses/_tick                       force daily tick (operator/debug)
```

`/summary` powers the sidebar widget (no full `/hypotheses` page yet —
operator decision: defer until ≥10 active rows justify it). `at_risk` =
active rows whose `expires_at` is within 30d.

## Frontend

[frontend/src/components/HypothesisStatusWidget.tsx](../frontend/src/components/HypothesisStatusWidget.tsx)
— sits below the sidebar nav in [Layout.tsx](../frontend/src/components/Layout.tsx).
At-a-glance: `active` count + `at_risk` count when > 0. Hides itself when
total = 0 so it's invisible until first row is seeded.

Hooks in [use-api.ts](../frontend/src/hooks/use-api.ts):
`useHypotheses(filters)`, `useHypothesis(id)`, `useHypothesisSummary()` (5min
poll), `useCancelHypothesis()`. Types in
[lib/types.ts](../frontend/src/lib/types.ts) — `Hypothesis`,
`HypothesisEvaluation`, `InvalidatorSpec`, `HypothesisSummary`.

## Seed script

`python scripts/seed_hypotheses.py [--rewrite]` reads every `*.md` (except
`template.md`) in `.claude/hypotheses/draft/`, normalises the
draft-frontmatter `claim_type` to our enum (`absolute → single_name`,
`regime_shift → regime`), and inserts rows. Two-pass: insert all rows
first, then resolve `parent_id` / `precondition_id` slug → UUID.

**DSL invalidators are seeded as `manual`.** Drafts express invalidators as
English bullets — not auto-translatable. Operator hand-authors the DSL via
`PATCH /v1/hypotheses/{id}` after seeding. The seed script logs a warning
to remind.

`--rewrite` updates `title`, `axis`, `primary_metric`, `tracking_signal`,
`body_md` on existing rows. Never touches `invalidator`, `status`, or `slug`
— operator authority is sacred for those.

## Out of scope (deferred)

- Full `/hypotheses` page. Sidebar widget covers M-2; defer page until ≥10
  rows make a card grid worthwhile. Operator decision 2026-05-01.
- Auto-translation of English invalidators → DSL via LLM. Punt to LLM phase.
- Wiring into Opportunities / Trades — M-3.
- LLM `/research/ask` grounding — M-4 (planned in
  [plans/M-2-then-content-then-llm.md](plans/M-2-then-content-then-llm.md)).
- Backtest replay of historical invalidator firings — M-6.
