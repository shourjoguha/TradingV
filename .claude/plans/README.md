# Plans

Detailed phase plans authored **before** execution. Each plan contains the
target shape, deliverables, files to touch, verification steps, and
sometimes a stress-test of failure modes.

Plans are immutable once their phase ships — corrections go into
[`../status/roadmap-shipped.md`](../status/roadmap-shipped.md) retros, not
back into the plan. This way the plan is a snapshot of "what we thought
before we built it" and the retro is "what actually happened."

## Index

| Plan | Phase | Status |
|---|---|---|
| [M-1-signal-layer.md](M-1-signal-layer.md) | Macro Workbench M-1 | shipped |
| [M-1f-frontend.md](M-1f-frontend.md) | Macro frontend | shipped |
| [M-2-hypothesis-object.md](M-2-hypothesis-object.md) | Hypothesis object + invalidator DSL | shipped |
| [M-2-then-content-then-llm.md](M-2-then-content-then-llm.md) | M-2 sequencing rationale | meta |
| [UI-consolidation.md](UI-consolidation.md) | Sidebar IA + density + tooltip standard | shipped |
| [folder-context-vignettes.md](folder-context-vignettes.md) | Vault folder-context render | shipped |
| [macro-workbench-brainstorm.md](macro-workbench-brainstorm.md) | Pre-plan: regime-aware research workbench (M-1..M-6) | brainstorm |
| [multi-watchlist-and-quotes.md](multi-watchlist-and-quotes.md) | MW-1 / MW-2 / MW-3 — roster split + boards + sector-drill | shipped |
| [phase-2-vault-indexer.md](phase-2-vault-indexer.md) | Knowledge layer + indexer sidecar | shipped |
| [phase-3-stress-test.md](phase-3-stress-test.md) | Research stress-test endpoint | shipped |
| [phase-3.7-research-ui-single-turn.md](phase-3.7-research-ui-single-turn.md) | Research UI v1 | shipped |
| [phase-3.8-research-ui-threading.md](phase-3.8-research-ui-threading.md) | Research threading | deferred |
| [video-channel-auto-ingest.md](video-channel-auto-ingest.md) | YouTube channel auto-ingest | shipped |
| [chart-modularity-handover.md](chart-modularity-handover.md) | Pre-plan: chart-modularity audit + stress-test checklist | meta |
| [charts-plotly-migration.md](charts-plotly-migration.md) | Charts infra reorg → Plotly (Phases 0-6) — full reference: [frontend/charts.md](../frontend/charts.md) | shipped |
| [charts-enrichment.md](charts-enrichment.md) | BumpChart + correlation drill-in + Tier 3 ChartBuilder (Phases A-E) | shipped |

## Pre-plans / brainstorms

Sometimes a brainstorm precedes the formal plan (e.g. `macro-workbench-brainstorm.md`
laid out the M-1..M-6 architecture before each phase got its own plan).
Keep these in this folder — they're a useful "north star" reference for
why the eventual plans took the shape they did.

## See also

- [`../status/roadmap-shipped.md`](../status/roadmap-shipped.md) — what actually shipped vs the plan
- [`../decisions/`](../decisions/) — ADRs that capture binding tradeoffs from these plans
- [`../guides/recipes.md`](../guides/recipes.md) — how to add a feature using existing patterns
- [`../../CLAUDE.md`](../../CLAUDE.md) — top-level reading paths

## Adding a new plan

1. Drop a markdown file here. Naming: `<phase-prefix>-<short-name>.md` (e.g. `phase-4.1-foo.md`, `MW-4-bar.md`).
2. Cross-link in [`../status/roadmap.md`](../status/roadmap.md).
3. After execution, drop a 1-2 ¶ retro in [`../status/roadmap-shipped.md`](../status/roadmap-shipped.md). Don't edit the plan post-ship.
