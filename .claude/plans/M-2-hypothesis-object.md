# M-2 — Hypothesis object + view registry (full plan)

> **Status:** Promoted from outline 2026-05-01. Execution **deferred to next session** by operator decision; this file is the contract for that work.
> **Source-of-truth design:** [macro-workbench-brainstorm.md](macro-workbench-brainstorm.md) § Hypothesis object.
> **Predecessor:** M-1 shipped (macro series ingestion, `compute_ratio()` query-time, ratio routes).

## Context

M-1 made the platform store macro series and compute ratios. M-2 adds the **claim layer** — a row per testable thesis with explicit invalidators that the platform evaluates daily, plus a **view registry** that lets the operator group claims into named workbench layouts. Five hand-authored drafts already live in [.claude/hypotheses/draft/](../hypotheses/draft/) and need ingest. M-3 will then wire hypotheses into Opportunities; M-4 layers an LLM `/research/ask`; M-6 is backtest replay. None of those are this milestone.

**Locked decisions inherited from outline (do not re-litigate):**

- Symbol references are strings — no FK from `hypothesis` to a series table.
- Ratios are read via `app.macro.service.compute_ratio()`; no precomputation.
- M-2 introduces zero ingestion. All data flows through M-1.
- View registry is markdown-with-frontmatter under `app/views/registry/*.md`, parsed at startup. **No DB table for views.**

**Locked from open questions:**

- **Q1 (invalidator language):** 5 ops only — `ratio_below_sma`, `series_above_threshold`, `series_below_threshold`, `series_change_pct`, `manual`. JSON shape pinned in §2 below.
- **Q2 (TTL defaults):** regime/breakout = 30mo, tactical = 6mo, single-name = 18mo. Stored explicitly per row at create time; no derived-at-read.
- **Q3 (cascade timing):** daily, aligned with M-1's nightly tick. **Not hourly** — invalidator semantics are fundamentally daily-resolution.

## 1. Schema — `migrations/versions/0021_hypotheses.py`

Two tables. Postgres-first; SQLite parity preserved via `sa.JSON` and string enum columns (no native enum).

### `hypothesis`

| col | type | notes |
|---|---|---|
| `id` | UUID PK | `uuid_generate_v4()` default |
| `slug` | TEXT UNIQUE NOT NULL | from frontmatter; URL-safe |
| `title` | TEXT NOT NULL | human-readable |
| `claim_type` | TEXT NOT NULL | enum-as-string: `regime` \| `tactical` \| `single_name` \| `breakout` |
| `axis` | TEXT NOT NULL | free-form taxonomy bucket (e.g. `liquidity`, `growth_vs_inflation`) |
| `parent_id` | UUID NULL FK→hypothesis(id) ON DELETE SET NULL | **sizing dependency** — child sizes off parent's confidence |
| `precondition_id` | UUID NULL FK→hypothesis(id) ON DELETE SET NULL | **existence dependency** — child auto-cancels if precondition violated |
| `primary_metric` | TEXT NOT NULL | the symbol or ratio expression the thesis predicts |
| `tracking_signal` | TEXT NOT NULL | the symbol/ratio the operator watches day-to-day |
| `invalidator` | JSONB NOT NULL | DSL — see §2 |
| `ttl_months` | INT NOT NULL CHECK (>0) | snapshotted from per-axis default at create time |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `expires_at` | TIMESTAMPTZ NOT NULL | computed: `created_at + ttl_months months` |
| `status` | TEXT NOT NULL DEFAULT 'active' | enum-as-string: `active` \| `expired` \| `invalidated` \| `cancelled` \| `manual_closed` |
| `body_md` | TEXT NULL | full markdown body from draft (post-frontmatter) — for read-back rendering |

Indexes: `(status, axis)`, `(precondition_id)`, `(parent_id)`, `(expires_at)`.

### `hypothesis_evaluation`

| col | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `hypothesis_id` | UUID NOT NULL FK→hypothesis(id) ON DELETE CASCADE | |
| `evaluated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `status_before` | TEXT NOT NULL | |
| `status_after` | TEXT NOT NULL | |
| `reason` | TEXT NOT NULL | one-line summary (`'invalidator: ratio_below_sma fired'`, `'ttl expired'`, `'cascade: precondition X cancelled'`, `'manual close'`) |
| `invalidator_result` | JSONB NULL | full DSL evaluation output for forensics — null for ttl/manual/cascade |

Index: `(hypothesis_id, evaluated_at DESC)`.

## 2. Invalidator DSL

Single shape: `{"op": "<name>", "args": {...}}`. Single evaluator entrypoint `app.hypotheses.invalidator.evaluate(spec, *, session) -> InvalidatorResult` where `InvalidatorResult` is `{fired: bool, observed: dict, reason: str}`.

| op | args | semantics |
|---|---|---|
| `ratio_below_sma` | `{numerator: str, denominator: str, sma_days: int, days_below: int}` | Fires when the ratio (M-1 `compute_ratio`) sits strictly below its `sma_days` SMA for `days_below` consecutive trading days. |
| `series_above_threshold` | `{symbol: str, threshold: float, days_above: int}` | Fires when raw series (M-1 `MacroSeries`) is `> threshold` for `days_above` consecutive days. |
| `series_below_threshold` | `{symbol: str, threshold: float, days_below: int}` | Mirror of above; `<` strict. |
| `series_change_pct` | `{symbol: str, window_months: int, threshold_pct: float, direction: 'up' \| 'down'}` | Fires when `(latest - last_eom_window_months_ago) / base * 100` crosses `threshold_pct` in `direction`. |
| `manual` | `{}` | Never fires automatically. UI surfaces a checkbox; only operator-driven `POST /v1/hypotheses/{id}/cancel` flips status. |

Implementation reuses [app/macro/service.py:compute_ratio](../../app/macro/service.py) for ratio reads and `MacroSeries` direct selects for raw series. No new DB queries shape — all read paths covered by M-1.

**Validator:** Pydantic discriminator on `op` field rejects unknown ops at create/update time → 422.

## 3. Routes — new module `app/hypotheses/`

Layout mirrors `app/boards/` (`__init__.py`, `models.py`, `schemas.py`, `service.py`, `routes.py`, `invalidator.py`). All endpoints behind `verify_api_key`.

```
GET    /v1/hypotheses?status=&axis=&claim_type=    list (filterable)
POST   /v1/hypotheses                              create (body validates DSL)
GET    /v1/hypotheses/{id}                         detail w/ recent evaluations
PATCH  /v1/hypotheses/{id}                         partial update (cannot change slug or ttl_months)
DELETE /v1/hypotheses/{id}                         hard delete (cascades evaluations)
POST   /v1/hypotheses/{id}/cancel                  manual close — body `{reason: str}`; writes evaluation row
GET    /v1/views                                   parsed registry map (in-memory)
```

Schemas (`schemas.py`):

- `HypothesisCreate` — title, slug, claim_type, axis, primary_metric, tracking_signal, invalidator, optional parent_id/precondition_id; `ttl_months` derived server-side from `claim_type`-→TTL map (regime/breakout=30, tactical=6, single_name=18).
- `HypothesisRead` — all columns + `recent_evaluations: List[EvaluationRead]` (last 10).
- `HypothesisPatch` — title, axis, primary_metric, tracking_signal, invalidator, parent_id, precondition_id (any subset).
- `HypothesisCancel` — `{reason: str}`.

Mount under `app/main.py` `app.include_router(hypotheses_router, prefix="/v1")`.

## 4. TTL defaults (locked)

```python
TTL_BY_CLAIM_TYPE = {
    "regime":      30,
    "breakout":    30,
    "tactical":     6,
    "single_name": 18,
}
```

Lives in `app/hypotheses/service.py`. `expires_at = created_at + relativedelta(months=ttl_months)`.

## 5. Lifespan loop — daily tick

Reuses existing scheduler in `app/main.py` lifespan. Single new function `app.hypotheses.service.run_daily_tick(session)` invoked per nightly tick. Three steps in order:

1. **TTL expiry**: `UPDATE hypothesis SET status='expired' WHERE status='active' AND expires_at < now()`. Bulk evaluation rows inserted with `reason='ttl expired'`.
2. **Invalidator evaluation**: For each row still `active`, dispatch `evaluate(invalidator)`. If `fired`, transition `active → invalidated`, write evaluation with full `InvalidatorResult`.
3. **Cascade**: For each row that just transitioned to `invalidated` in step 2 (or was already invalidated/cancelled and has children), find rows where `precondition_id = parent_id AND status='active'`, set them to `cancelled`, write evaluation with `reason='cascade: precondition <slug> invalidated'`.

Cascade is recursive — if cancelled child has its own children via `precondition_id`, they cancel too. Use iterative worklist; bound iterations at 10 (more = circular precondition graph; log + abort).

## 6. View registry — `app/views/`

New module: `app/views/__init__.py`, `app/views/parser.py`, `app/views/registry/*.md`. No DB.

**Frontmatter schema** (per `.md`):

```yaml
---
id: macro_liquidity                # UNIQUE within registry
title: "Liquidity & Credit"
default_axis: liquidity
panels:
  - {kind: ratio,  numerator: "WALCL", denominator: "GDP", sma_days: 200}
  - {kind: series, symbol: "DGS10",   threshold: 4.5}
  - {kind: hypothesis_filter, axis: "liquidity"}
---
# Body — operator notes about this view (rendered in UI tooltip)
```

Parsed once at app startup into `app.views.registry: dict[str, ViewSpec]`. Pydantic model validates each frontmatter; parse errors fail boot loudly (better than silent half-loaded registry). `GET /v1/views` returns `{id: ViewSpec}`.

## 7. Frontend — new page `/hypotheses`

File: `frontend/src/pages/Hypotheses.tsx`. Lazy-loaded route, sidebar entry under existing **Decisions** group (sibling to Watchlists).

Components — all reuse existing neumorphic primitives (`Card`, `Badge`, `Select`, `ToggleGroup`, `EmptyState`, `InfoBubble`).

- **Header**: title + InfoBubble pulling from new glossary entry `hypothesis_concept`.
- **Filter bar**: 3 chip groups — `axis` (dynamic from response), `status` (active|expired|invalidated|cancelled|manual_closed), `claim_type` (regime|tactical|single_name|breakout). Multi-select within each group.
- **Card grid**: one card per hypothesis. Status pill (color-coded), TTL countdown (`expires in 14mo` / `expired 3d ago`), tracking_signal mini-sparkline (reuse `RatioChart` for ratio specs, plain line otherwise — feeds via existing macro endpoints), invalidator one-liner ("ratio WALCL/GDP < 200d SMA for 30d"), parent/precondition chips with click-to-filter.
- **Manual-close button**: visible only when `invalidator.op === 'manual'` AND `status === 'active'`. Opens dialog → `POST /v1/hypotheses/{id}/cancel`.
- **Detail drawer** (click card): full markdown body via existing `DocViewer`; recent_evaluations timeline.

New types in [frontend/src/lib/types.ts](../../frontend/src/lib/types.ts) — `Hypothesis`, `HypothesisEvaluation`, `InvalidatorSpec` (discriminated union over the 5 ops), `ViewSpec`.

New hooks in [frontend/src/hooks/use-api.ts](../../frontend/src/hooks/use-api.ts) — `useHypotheses(filters)`, `useHypothesis(id)`, `useCreateHypothesis`, `useUpdateHypothesis`, `useCancelHypothesis`, `useViews`.

App routing: `frontend/src/App.tsx` — lazy route `/hypotheses` + sidebar entry.

## 8. Seed script — `scripts/seed_hypotheses.py`

Standalone CLI (`python scripts/seed_hypotheses.py [--rewrite]`). Reads every `.md` in `.claude/hypotheses/draft/` except `template.md`, parses frontmatter (`python-frontmatter` lib already in `requirements.txt`? — verify; if not add), maps the existing draft fields to the row schema:

| draft frontmatter | row column | mapping |
|---|---|---|
| `name` | `title` | as-is |
| `slug` | `slug` | as-is |
| `expected_dir` | (informational only — not stored) | — |
| `claim_type` | `claim_type` | drafts use `absolute`/etc.; **add a normalization step**: `absolute → single_name`, `regime_shift → regime`, otherwise pass-through. Reject unknown values with clear error. |
| `primary_metric` | `primary_metric` | as-is |
| `tracking_signal` | `tracking_signal` | as-is |
| `ttl_months` | `ttl_months` | as-is — drafts **override** the per-axis default. Document this in the seed script. |
| `parent_id` (slug) | `parent_id` (UUID) | resolve via second pass — load all rows, rewrite slug→UUID. Two-pass insert. |
| `invalidators` (plain English list) | `invalidator` (DSL JSON) | **NOT auto-translatable** — drafts express invalidators as English bullets. Strategy: seed with `{"op": "manual", "args": {}}`, log a warning per row noting the operator must hand-author the DSL via `PATCH /v1/hypotheses/{id}` after seeding. This is acceptable for M-2 (5 rows, operator already wrote them). |
| body | `body_md` | full markdown post-frontmatter |

Idempotency: `INSERT ... ON CONFLICT (slug) DO NOTHING` by default; `--rewrite` flag updates `title`, `body_md`, `tracking_signal`, `primary_metric` (NOT slug, NOT invalidator — operator's DSL edits are sacred). Status set to `active`; `expires_at = now() + ttl_months months`.

## 9. Tests — `tests/test_hypotheses.py`

Approximately 25 tests across:

- **CRUD round-trips** (5): create→get→list→patch→delete. Slug uniqueness 409.
- **Invalidator DSL validation** (6): one happy + one rejected (unknown op / bad arg shape) per spec category, plus malformed JSON.
- **Invalidator evaluation** (5, one per op): synthetic `MacroSeries` rows in fixture, assert `fired=true/false` matches expected.
- **Lifespan tick — TTL expiry** (1): row with `expires_at` in past → tick → status=expired + evaluation row.
- **Lifespan tick — invalidator fires** (1): row with `ratio_below_sma` matching synthetic data → tick → status=invalidated.
- **Lifespan tick — cascade** (2): precondition violation cancels child; recursive grandchild also cancelled. Bounded loop terminates on circular graph.
- **Manual cancel** (1): POST cancel writes evaluation, status=manual_closed.
- **View registry** (3): valid registry parses to expected dict; invalid frontmatter fails boot (raises); `GET /v1/views` returns parsed map.
- **Seed script idempotency** (1): run twice, assert row count stable, no error.

Use existing `tests/conftest.py` patterns (in-memory SQLite via `create_all`). Register new models in conftest's metadata import block (boards is the prior reference).

## 10. Critical files (all NEW unless marked EDIT)

**Backend**

- `migrations/versions/0021_hypotheses.py`
- `app/hypotheses/__init__.py`
- `app/hypotheses/models.py`
- `app/hypotheses/schemas.py`
- `app/hypotheses/service.py`
- `app/hypotheses/routes.py`
- `app/hypotheses/invalidator.py`
- `app/views/__init__.py`
- `app/views/parser.py`
- `app/views/routes.py`
- `app/views/registry/macro_liquidity.md`
- `app/views/registry/macro_growth_inflation.md`
- (more views to be authored opportunistically — registry is additive)
- **EDIT** `app/main.py` — wire `/v1/hypotheses` + `/v1/views` routers; call `run_daily_tick` from lifespan loop; load view registry at startup.
- **EDIT** `app/core/db.py` — register hypotheses models in metadata for `create_all` parity.
- **EDIT** `tests/conftest.py` — register hypotheses models for test create_all.
- `tests/test_hypotheses.py`
- `scripts/seed_hypotheses.py`

**Frontend**

- `frontend/src/pages/Hypotheses.tsx`
- **EDIT** `frontend/src/lib/types.ts` — append `Hypothesis`, `HypothesisEvaluation`, `InvalidatorSpec`, `ViewSpec`.
- **EDIT** `frontend/src/hooks/use-api.ts` — append 6 hooks.
- **EDIT** `frontend/src/App.tsx` — lazy route + sidebar entry.
- **EDIT** `frontend/src/lib/glossary.ts` (or wherever glossary lives — verify) — `hypothesis_concept` entry.

**Docs**

- `.claude/hypotheses.md` (module doc)
- `.claude/views.md` (module doc)
- `.claude/decisions/012-hypothesis-object.md` (ADR — captures locked decisions: TTL defaults, daily cascade, manual-DSL seed strategy, view registry as files-not-DB)
- **EDIT** `CLAUDE.md` — append rows to module table.
- **EDIT** `.claude/glossary.md` — add `hypothesis`, `invalidator`, `precondition`, `view` terms.
- **EDIT** `.claude/roadmap.md` — move M-2 from candidate to active; add M-3 wiring intent.

## 11. Verification (UAT — what "M-2 ships" means)

Run in order; each must pass before the next.

1. `alembic upgrade head` clean — both tables created, indexes present.
2. `python -m pytest tests/test_hypotheses.py -v` 100% pass; no flakes.
3. `python -m pytest` full suite green (no regressions in 289 prior tests).
4. `python scripts/seed_hypotheses.py` ingests 5 drafts (skipping `template.md`); `GET /v1/hypotheses` returns 5 rows; warning log present for hand-DSL TODO.
5. `GET /v1/views` returns the parsed registry map (>=2 entries).
6. Browser at `/hypotheses`: 5 cards render; filter chips narrow the grid; status pills color-coded; manual-close button present on `manual` invalidators only.
7. Click a card with `precondition_id` set → drawer shows precondition chip → click chip → grid filters to that row.
8. Force-fire lifespan tick (debug endpoint `POST /v1/_debug/run_hypothesis_tick` — gated to dev env only) on a fixture with `expires_at` in past → status flips to `expired`, evaluation row written, UI reflects on next refetch.
9. Manual close one card → status flips to `manual_closed`; evaluation row visible in detail drawer timeline.
10. Restart app with a deliberately-broken view registry file (bad frontmatter) → boot fails with clear error; revert; boot succeeds.

## 12. Cross-references

- Outline this replaces (now deleted/overwritten): same file, prior version pinned at git ref before this commit.
- M-1 reuse: [app/macro/service.py](../../app/macro/service.py) `compute_ratio`; [app/macro/models.py](../../app/macro/models.py) `MacroSeries`.
- Module pattern reference (mirror this layout): [app/boards/](../../app/boards/) (MW-2).
- Frontend page pattern reference: [frontend/src/pages/Watchlists.tsx](../../frontend/src/pages/Watchlists.tsx) (MW-2 — chip filters + cards + detail drawer).
- Drafts to ingest: [.claude/hypotheses/draft/](../hypotheses/draft/).

## 13. Out of scope (do not bleed into M-2)

- Wiring hypotheses into Opportunities or Trades (M-3).
- LLM `/research/ask` endpoint that consults hypothesis state (M-4).
- Backtest replay of historical invalidator firings (M-6).
- Auto-translation of English invalidators into DSL — punt to operator hand-edit; revisit only if seed scales beyond ~20 drafts.
- Hourly cascade — explicitly rejected (Q3 lock).
- Per-hypothesis Telegram notification on status flip — backlog candidate; not M-2.
