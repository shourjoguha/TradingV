# ADR-013: Hypothesis object — schema, DSL, cascade timing, ship-shape

**Date**: 2026-05-01
**Status**: Accepted (M-2 shipped)

## Context

The platform had predictions, accuracy attribution, opportunities, trades,
and macro panels — all *descriptive of the world*. Nothing structured about
*what the operator believes about the world*. Beliefs lived in
`.claude/hypotheses/draft/*.md` as read-only Claude context. They didn't
auto-flip when invalidators fired, didn't cascade-cancel children when
preconditions broke, didn't expire on TTL, and weren't queryable from
elsewhere on the platform.

M-2 introduces the hypothesis layer. Several decisions were not obvious from
the brainstorm and needed locking before implementation.

## Decisions

### 1. Status enum-as-string, not Postgres ENUM

Five values: `active | expired | invalidated | cancelled | manual_closed`.
Stored as `String(32)`, not `sa.Enum`. **Reason:** SQLite test parity. Adding
a 6th status later requires no migration. We accept the lack of DB-level
enforcement — the route layer + Pydantic validate, and the operator is the
sole writer.

### 2. Invalidator DSL: 5 ops, no more

`ratio_below_sma`, `series_above_threshold`, `series_below_threshold`,
`series_change_pct`, `manual`. **Reason:** every additional op multiplies
the test surface and the validator complexity. Five covers every draft we
have. Adding a 6th = a new ADR. The `manual` op exists explicitly so
invalidators-as-prose drafts can be ingested without auto-translation
(operator hand-edits via PATCH).

### 3. Cascade is daily, not hourly

Same nightly tick as M-1's macro ingestion. **Reason:** invalidator semantics
(`days_below`, `window_months`, etc.) are fundamentally daily-resolution.
Hourly evaluation buys nothing real and burns N×24 evaluations / day for
no signal change.

### 4. TTL stored explicitly, not derived

`ttl_months` is a column, snapshotted at create time from per-claim_type
defaults. Operator override wins. **Reason:** drafts already override the
defaults (`btc-bottom-3m` is `regime` claim_type but `ttl_months=3`). A
"derive at read time" approach would have required a separate
`ttl_overrides` field. Storing it directly is simpler.

### 5. `expires_at = created_at + ttl_months × 30 days`

Approximation, not calendar months. **Reason:** avoids a `python-dateutil`
dependency for what's a daily-resolution cutoff. ≤2 days/year drift; harmless.

### 6. View registry is files, not a table

`app/views/registry/*.md` parsed at boot into an in-memory dict. **Reason:**
- Editing a view = editing a file. No CRUD UI to build.
- Git-diffable. Every operator change captured.
- Adding a new panel kind requires no migration.

Boot fails loudly on parse error so the operator sees broken files
immediately rather than a silent half-loaded registry.

### 7. Foreign keys are `ON DELETE SET NULL`, not `CASCADE`

`parent_id` and `precondition_id` self-references. **Reason:** deleting a
parent should NOT silently delete its children. Operator audits the
orphans. `hypothesis_evaluation` does cascade because evaluations are
hypothesis-private records.

### 8. Cascade is bounded recursive

`_cascade_pass` iterates up to 10 times. **Reason:** circular precondition
graphs are operator error but shouldn't hang the tick. Bound-and-log
means the operator sees the issue without losing the tick. Tests cover
the recursive-grandchild path.

### 9. Seed script writes `manual` invalidator

The 5 existing drafts express invalidators as English bullets. **Reason:**
- Auto-translation requires LLM (M-4 territory).
- Operator already wrote them; hand-translation in `PATCH` calls is a
  one-time cost.
- `manual` placeholder ensures rows exist + are queryable from M-3 day 1
  even before DSLs are typed in.

### 10. Ship the page small — sidebar widget only

Full `/hypotheses` page is the most expensive piece of M-2 scaffolding for
the *least* downstream-blocking value. **Reason:** with only 5 seed rows,
a card grid is overkill. Sidebar widget (`active` count + `at_risk` count
when > 0) covers the awareness need. Defer the page until ≥10 active rows
justify it. M-3 doesn't depend on the page — it depends on the queryable
table.

## Consequences

- Code: ~720 lines backend, ~100 lines frontend (widget + types + hooks),
  ~330 lines tests. Shipping cost in line with previous module additions.
- 23 new tests, full suite 314 passing, no regressions.
- Operator owes ~30 minutes of post-seed work to type DSL invalidators
  for the 5 drafts. Post-M-2 backlog item.
- Phase 2 (content layer) and Phase 3 (LLM stack) can FK to `hypothesis.id`
  immediately. No further M-2 dependency on operator hand-editing — the
  rows exist, FKs resolve.

## Alternatives considered

- **Postgres ENUM types** for status / claim_type — rejected for SQLite
  parity (see #1).
- **JSONB invalidator** with native indexing — Postgres-specific, breaks
  SQLite tests. Plain `JSON` chosen; Postgres can index later if a query
  path warrants.
- **No DSL — store English bullets, evaluate via LLM at tick time** —
  cost too high (LLM call per row per day), nondeterministic, hard to
  test. Locked DSL is boring and that's the feature.
- **Hourly evaluation tick** — rejected (#3).
- **Full /hypotheses page in M-2** — rejected (#10).
