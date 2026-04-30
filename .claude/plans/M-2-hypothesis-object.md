# M-2 — Hypothesis object + view registry (outline only)

> **Status:** Pending. M-1 must ship first.
> **Outline only.** Full plan written when M-2 promotes from candidate to active.
> **Source-of-truth design:** [macro-workbench-brainstorm.md](../macro-workbench-brainstorm.md)

This file exists so M-1's choices don't paint M-2 into a corner. Skim before finalising any M-1 schema decision.

## Locked decisions M-2 will rely on

- M-1 stores macro values keyed `(symbol, ts)`. M-2 references symbols by string — no foreign key.
- M-1 ratios computed at query time. M-2 invalidator engine reads ratios via `compute_ratio()` (M-1's service).
- M-2 will not introduce its own ingestion. All data flows through M-1.

## What M-2 adds

- Tables: `hypothesis`, `hypothesis_evaluation`. Schema sketch lives in [brainstorm.md § Hypothesis object](../macro-workbench-brainstorm.md).
- New schema fields beyond initial sketch (pinned 2026-04-30):
  - `slug` UNIQUE
  - `parent_id` (sizing dependency)
  - `precondition_id` (existence dependency, auto-cancel on violation)
  - `claim_type` enum
  - `primary_metric`, `tracking_signal`
- View registry — markdown files with frontmatter, parsed at startup. No DB table for views.
- Routes: `GET/POST/PATCH/DELETE /v1/hypotheses`, `POST /v1/hypotheses/{id}/cancel`, `GET /v1/views`.
- Lifespan loop: nightly status recompute (TTL expiry, invalidator evaluation, cascade for precondition violations).
- Frontend: new `/hypotheses` page using existing neumorphic primitives. Cards + status pills + filter chips.
- Ingest the 5 seeded drafts in [`hypotheses/draft/`](../hypotheses/draft/) — one-shot script that reads the markdown, inserts rows.

## Things M-2 will NOT do (deferred to M-3+)

- Any wiring into `Opportunities` or `Trades`. That's M-3.
- LLM `/research/ask` endpoint. That's M-4.
- Backtest replay. That's M-6.

## Open questions that will surface in M-2 planning

1. **Invalidator language.** Brainstorm flagged "small enumerated set" — need to lock the list. Candidate set:
   - `ratio_below_sma(num, denom, sma_days, days_below)`
   - `series_above_threshold(symbol, threshold, days_above)`
   - `series_below_threshold(symbol, threshold, days_below)`
   - `series_change_pct(symbol, window_months, threshold_pct, direction)`
   - `manual` (operator-evaluated; surfaces as a checkbox on the hypothesis card)
2. **TTL defaults per axis.** Long-horizon (regime/breakout) → 24-36mo. Tactical (timing) → 3-6mo. Single-name conviction → 12-18mo.
3. **Status cascade timing.** Recompute hourly or daily? Probably daily aligned with M-1's nightly tick. Avoid hourly — invalidator semantics are fundamentally daily-resolution.

## Cross-session continuity

When M-2 promotes, copy the brainstorm hypothesis-schema block + this file into a full plan at `.claude/plans/M-2-hypothesis-object.md` (overwrite this outline) and proceed.
