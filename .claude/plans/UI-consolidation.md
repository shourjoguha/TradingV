# UI Consolidation — Phases A → E

> **Status:** ✅ ALL FIVE PHASES SHIPPED 2026-04-30.
> **Scope:** Five sequential phases. Test green required between phases; commit after each.
> **Skills consulted:** `ui-ux-pro-max` (IA + dashboard archetypes + UX guidelines), `frontend-design` (component patterns).
> **Constraint:** Neumorphic light theme is locked. No dark mode, no glassmorphism.
> **Cross-session resume:** A fresh session reads this file + the latest commit's `git log` between `561918a` and `HEAD`; the next-pending todo entry indicates where to resume.

## Pre-execution state (locked snapshot)

- Last shipped: M-1f Macro frontend (commit `561918a`).
- Working tree clean.
- 269/269 backend tests green.
- Frontend `tsc --noEmit` clean.
- Live backend: `http://localhost:8000`, healthy.
- Frontend dev server: `http://localhost:3000`.

If any of those flip during execution, halt and capture the flip in this doc before continuing.

---

## Phase A — Sidebar IA

### Operator-locked structure

```
1. Dashboard                                /
2. Decisions
   1. Macro                                 /macro/:tab?      (tabs: overview / ratios / sectors)  ← unchanged
   2. Predictions                           /predictions/:tab? (tabs: horizon / target)            ← NEW wrapper
   3. Motion                                /motion/:tab?      (tabs: opportunities / trades)     ← NEW wrapper
3. Admin
   1. Watchlist                             /watchlist
   2. Schedule                              /schedule
   3. Health                                /health           (rebrand of /analysis; same pages)
4. Docs                                     /docs/:slug?       ← already nested; just relabel sidebar group
   1. Metrics & Definitions                 /docs/metrics
   2. How to use                            /docs/how-to-use
```

### Routing changes

| Old | New | Behavior |
|---|---|---|
| `/predictions/by-target` | `/predictions/target` | Old → `Navigate replace` to new |
| `/predictions/by-horizon` | `/predictions/horizon` | Old → `Navigate replace` |
| `/opportunities` | `/motion/opportunities` | Old → `Navigate replace` |
| `/trades` | `/motion/trades` | Old → `Navigate replace` |
| `/analysis` | `/health` | Old → `Navigate replace` |
| `/analysis/:jobId` | `/health/:jobId` | Old → `Navigate replace` |
| `/macro/:tab?` | unchanged | — |
| `/docs/:slug?` | unchanged | — |
| `/watchlist`, `/schedule`, `/` | unchanged | — |

Redirects implemented as `<Route element={<Navigate to="..." replace />} />` so deep-linked old URLs still work.

### Sidebar implementation

`Layout.tsx`:
- Replace flat `NAV` array with grouped `NAV_GROUPS: { label, children: [{ path, label, icon? }] }[]`.
- Render: section header (small caps, muted) + collapsible children with chevron.
- Single child group (Dashboard, Docs as a route alone) renders as a leaf, not a section.
- Section auto-expanded when one of its children is the active route.
- Persist collapse state in `localStorage('sidebar.collapsed')` keyed by group label.
- Active state: child highlight + parent section subtle accent.

Reuse the segmented-tabs pattern from `Macro.tsx` for the new `Predictions.tsx` and `Motion.tsx` wrapper pages. Wrappers are thin — they just render the sub-tab control + the existing page components.

### New / changed files

- `frontend/src/pages/Predictions.tsx` — wrapper with sub-tabs `horizon | target` (defaults to `horizon`). Renders existing `PredictionsByHorizon` / `PredictionsByTarget` based on tab.
- `frontend/src/pages/Motion.tsx` — wrapper with sub-tabs `opportunities | trades` (defaults to `opportunities`). Renders existing `Opportunities` / `Trades`.
- `frontend/src/pages/Health.tsx` — thin alias of `AnalysisJobs` exported as `Health` for the rebrand. Or just rename and add `Health = AnalysisJobs` re-export — internal naming stays `AnalysisJobs` since the data shape is jobs.
- `frontend/src/components/Layout.tsx` — replace `NAV` with `NAV_GROUPS`; new `<NavGroup>` component.
- `frontend/src/App.tsx` — new routes + redirects.

### Phase A verification

- TS clean.
- Click each sidebar entry; deep-link old URLs (`/opportunities`, `/by-horizon` etc.) and confirm redirect.
- Sub-tabs in Predictions and Motion behave like Macro's — segmented control, URL reflects tab.
- Browser console: zero errors.
- Backend test suite (`pytest -q`) still green (no backend touched but enforce the gate).

### Phase A risks

- Old links / bookmarks / tests referencing old routes. Mitigation: redirects.
- Tests in `tests/test_*.py` don't reference frontend routes (verified earlier).
- Cypress / Playwright e2e — none in repo. Skip.

---

## Phase B — Dashboard rebuild

### Goal

`/` becomes the operator's morning-glance view. Two axes of information:

- **Above the fold:** is the system healthy? + what's the current macro regime?
- **Below the fold:** what's actionable today (opportunities), recent activity, queue.

### Layout

Three-row composition, neumorphic cards throughout:

```
┌─────────────────────────────────────────────────────────────┐
│  Row 1 — Regime strip (4 inline cards, one per regime axis) │
│  Inflation | Growth | Liquidity | Stress                    │
│  Each card: top ratio's name + Δ% over 1Y + sparkline       │
│  Click a card → /macro                                      │
└─────────────────────────────────────────────────────────────┘
┌──────────────────────┐ ┌─────────────────────┐ ┌───────────┐
│  Row 2 — Two-thirds  │ │  Row 2 — One-third  │ │  Schedule │
│  Latest Opportunity  │ │  Accuracy summary   │ │  status   │
│  card with action    │ │  (n, hit, MAPE)     │ │  + Run-now│
│  Recent jobs (3)     │ │                     │ │           │
└──────────────────────┘ └─────────────────────┘ └───────────┘
```

Mobile: stacks vertically.

### Components

- `frontend/src/components/dashboard/RegimeStrip.tsx` — 4 cards, each pulling the *first* row from each `REGIME_PANELS[]` axis (the "headline" ratio). Reuses `Sparkline` from `components/macro/`.
- `frontend/src/components/dashboard/AccuracyTile.tsx` — pulls top of `useAccuracyGrid` for the operator's current watchlist. Compact: avg hit-rate, avg MAPE, n.
- `frontend/src/components/dashboard/LatestOpportunity.tsx` — `useOpportunities({ status: 'pending', limit: 1 })`. Card with rule names + predicted move + jump to `/motion/opportunities`.
- Reuse the existing schedule + recent-jobs tiles from current `Dashboard.tsx`; relayout, don't rebuild.

### Files

- `frontend/src/pages/Dashboard.tsx` — heavy edit, ~70% rewrite.
- `frontend/src/components/dashboard/{RegimeStrip,AccuracyTile,LatestOpportunity}.tsx` — new.

### Phase B verification

- TS clean.
- Dashboard renders without errors with live laptop backend.
- Regime strip shows non-zero data for each of 4 axes.
- Latest-opportunity card renders empty-state correctly when no pending opps.
- Click each tile → routes to the correct deep-link.

---

## Phase C — Density / rhythm pass

### Goals

One visual rhythm across pages. Audit deltas observed in pre-execution audit:

- Empty states: 5 different shapes today.
- Loading skeletons: 3 different.
- Card padding: inconsistent (`p-3` / `p-4` / `p-6` mixed).
- Header treatment: some pages have description, some don't; some use `<h2>` with `text-2xl`, others `text-xl`.

### Standards to enforce

- **Page header**: always `<h2 className="text-2xl font-heading font-semibold tracking-tight">` + paragraph below in `text-muted-foreground text-sm`. Right-side controls (refresh, filters) align baseline.
- **Empty state component**: `<EmptyState icon={Icon} title="..." description="..." action?={...} />` in `components/common/`. Replaces all hand-rolled empty divs.
- **Loading skeleton**: same ad-hoc skeletons → `<TableSkeleton rows={3} />`, `<CardSkeleton />` shared shapes.
- **Card padding**: `p-6` for top-level cards, `p-3` for nested rows, `p-4` for medium-density cards. Document in `frontend/src/components/ui/card.tsx` JSDoc.
- **Section gap**: `space-y-6` on page root, `space-y-4` inside cards. Lock these.

### Files

- `frontend/src/components/common/EmptyState.tsx` — new.
- `frontend/src/components/common/PageHeader.tsx` — new.
- `frontend/src/components/common/LoadingStates.tsx` — `TableSkeleton`, `CardSkeleton`.
- All pages: replace hand-rolled empty / loading / header blocks. Use `git grep` to find them systematically.

### Phase C verification

- TS clean.
- Visit every page in the browser; visually confirm consistent spacing, header weight, empty-state look.
- No regressions on sidebar / routing from Phase A.

---

## Phase D — Tooltip standard + `<InfoBubble>` definitions

### Goals

1. Standardize on **two** ephemeral patterns: `<HoverTooltip>` (small key/value) and `<HoverPopover>` (rich content). No third.
2. Add `<InfoBubble term="hit_rate" />` — small `(i)` circle next to any data label or ratio. Hover → glossary definition pulled from a single source of truth.

### Single source of truth for definitions

`frontend/src/lib/glossary.ts` — registry:

```ts
export const GLOSSARY = {
  hit_rate: {
    short: "Directional accuracy",
    long: "Fraction of predictions whose direction matched the actual move from baseline. Doesn't account for magnitude.",
    docHref: "/docs/metrics#hit-rate",
  },
  mape: { ... },
  delta_pct: { ... },
  baseline_close: { ... },
  ratio_macro: { ... },
  // ... 30+ terms harvested from .claude/glossary.md and frontend/src/docs/metrics.md
} as const;
```

`<InfoBubble>` reads this registry and renders a small circle + hover popover with the long definition + a "Read more" link to `/docs/metrics#anchor`.

### Components

- `frontend/src/components/common/HoverTooltip.tsx` — replaces the various per-page hover implementations.
- `frontend/src/components/common/HoverPopover.tsx` — the OHLC mini-candle on `/predictions/horizon` and the per-prediction breakdown on `/accuracy` migrate to this.
- `frontend/src/components/common/InfoBubble.tsx` — the `(i)` circle + glossary lookup.
- `frontend/src/lib/glossary.ts` — registry.

### Refactors

- `PredictionsByHorizon.tsx` — keep the candle tooltip (operator likes it); migrate the wrapper to `<HoverPopover>`.
- `Accuracy.tsx` — drill panel → `<HoverPopover>` (or keep inline panel — decide based on aesthetic during execution).
- `Macro.tsx`, `Dashboard.tsx`, `Accuracy.tsx`, etc. — sprinkle `<InfoBubble>` next to non-obvious labels.

### Phase D verification

- TS clean.
- Hover an `<InfoBubble>` on Macro → popover with definition + link.
- Existing tooltips on `/predictions/horizon` still work (operator-protected feature).
- Click "Read more" link → routes to `/docs/metrics#hit-rate` and scrolls to the heading (relies on `rehype-slug`'s anchor IDs from existing Docs hub).

---

## Phase E — Mobile pass

### Goals

Operator-on-phone is functional. Specifically:

- Sidebar → mobile drawer (`< md`) — already implemented in `Layout.tsx`. Verify still works after Phase A grouping.
- Tables that exceed viewport → collapse to card list on `< sm`.
- No horizontal scrolling on iPhone width (`375px`).

### Audit targets (suspects from earlier review)

- `PredictionsByHorizon.tsx` — wide matrix table.
- `AnalysisJobs.tsx` (now `Health.tsx`) — wide row table with expandable detail.
- `Trades.tsx` — table layout.
- `Watchlist.tsx` — table layout.

For each suspect: at `< sm`, render row as a stacked card with key/value pairs. Existing patterns from `Macro.tsx`'s sector strip (3-col grid on mobile) are the model.

### Components

- `frontend/src/components/common/ResponsiveTable.tsx` — tiny helper that switches between `<table>` (md+) and a stacked card list (sm). Optional; may decide it's overkill and inline the breakpoint logic per page.

### Phase E verification

- Resize browser to 375px (`mcp__Claude_Preview__preview_resize` preset `mobile`).
- Visit every page; confirm no horizontal scroll, all controls reachable.
- Sidebar drawer opens + closes from the hamburger.
- Test on `tablet` preset too (768px).

---

## Cross-session resume protocol

1. Read this file.
2. Read the latest todo state in the active session (or `git log --oneline 561918a..HEAD`).
3. If a phase is mid-execution, check `git status` — uncommitted changes = mid-phase, no commit yet = phase isn't verified.
4. Each phase commits independently with a clear subject — easy to identify the boundary.
5. Test gates between phases. If pytest or `tsc` fails, halt and document in this file's "Known issues" section before resuming.

## Known issues / deviations

(none yet)

## Estimated total effort

| Phase | Estimate |
|---|---|
| A | 1-1.5 h |
| B | 2-3 h |
| C | 2-3 h |
| D | 2-3 h |
| E | 1-2 h |
| **Total** | **8-12 h focused** |

If session compacts mid-phase, resume from the next-uncommitted phase. If session compacts mid-commit (rare), `git reset HEAD~1 --soft` and re-stage.
