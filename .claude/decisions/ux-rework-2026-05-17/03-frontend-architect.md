# 03 — Frontend Architect voice

**Reviewer**: Frontend Architect (component reuse, hook organization, URL-state, layout primitives, type-safety).
**Stack**: Vite 5 + React 18 + TS + react-router-dom v6 + TanStack Query v5 + Tailwind 3 + handwritten shadcn primitives.
**Scope boundary**: information layer (`tools/vault_indexer/`, `tools/ingest/`) is OUT. Backend changes minimized — recommend `openapi-typescript` (devDep already present) instead of hand-rolling parallel types.

---

## Architectural issues (severity-ranked)

### 1. **DriftBar duplicated three ways** — SEV: HIGH (correctness + visual drift)
Three independent implementations of the same scalar-to-bar widget exist:
- `components/today/RxStrip.tsx:33-47` — width `w-12`, height `h-1.5`, thresholds `>70/>40`.
- `pages/RxFinance.tsx:34-46` — width `w-16` (different!), same thresholds.
- `pages/RxFinanceDetail.tsx:120` — text-only fallback (`r.drift_score.toFixed(2)`), no bar.
- `pages/Trades.tsx:262` — bare `.toFixed(2)`.
Every operator-visible drift signal looks different depending on which page they're on.
**Proposed primitive**: `components/common/DriftBar.tsx` accepting `{ score, size: 'sm'|'md'|'lg' }`. Re-point all four call sites. ~30 LOC, net deletion ~50 LOC.

### 2. **TabbedShell pattern hand-rolled 6+ times** — SEV: HIGH (largest single dup)
`pages/Motion.tsx:53-83`, `pages/Predictions.tsx:23-49`, `pages/Macro.tsx:91-113`, `pages/Admin.tsx:44-67`, `pages/TheStreet.tsx:~30-60`, `pages/ThesesShell.tsx`, `pages/WatchlistConsolidated.tsx` all implement: `useParams({ tab })` → resolve to typed enum with default → render `<div role="tablist">` with identical Tailwind (`inline-flex rounded-xl bg-background shadow-inset-sm p-1 gap-1`) → `tab === 'x' && <X />`. ~50 LOC per page × 7 = ~350 LOC of pure boilerplate.
**Proposed primitive**: `components/common/TabbedShell.tsx`:
```ts
<TabbedShell
  basePath="/motion"
  defaultTab="opportunities"
  tabs={[
    { id: 'opportunities', label: 'Opportunities', render: () => <Opportunities /> },
    { id: 'trades', label: 'Trades', render: () => <Trades /> },
  ]}
/>
```
Handles routing, ARIA, lazy-mount fallback, and the canonical pill styling. Net deletion ~300 LOC after migration.

### 3. **No DataTable primitive; 5+ hand-rolled tables** — SEV: HIGH
`Trades.tsx`, `Opportunities.tsx`, `RxFinance.tsx:76-120`, `RxFinanceHypotheses.tsx:42-86`, `RxFinancePositions.tsx`, `Hypotheses` view, `Watchlists.tsx`, `AnalysisJobs.tsx` all duplicate the same table chrome: `<table className="w-full text-sm">` + `<thead>` with the exact `text-xs font-semibold uppercase tracking-wider text-muted-foreground` columns + `<tr className="border-t border-border/40">` row pattern. None share sort/filter/empty/loading state. Empty-state styling itself is duplicated in `RxFinance.tsx:69-73` despite `components/common/EmptyState.tsx` existing.
**Proposed primitive**: `components/common/DataTable.tsx<T>` with `{ columns, rows, isLoading, emptyState, onRowClick, sort?, defaultSort? }`. Wraps `components/ui/table.tsx`. Net deletion ~400 LOC.

### 4. **`hooks/use-api.ts` is 1832 LOC, single file, 70+ hooks** — SEV: MEDIUM
Counted exports at `use-api.ts:65..1464`. Cohesion is broken — TV-context, research, rx, accuracy, opportunities, trades, watchlist, macro, admin, hypotheses all share one module. Bundle-splitting is impeded (TanStack mutation hooks pull all sibling helpers into the entry chunk). Touching ANY hook invalidates HMR for every consumer page.
**Proposed split**: `hooks/api/{accuracy,opportunities,trades,rx,research,tv-context,macro,admin,hypotheses,watchlist,queue}.ts` with a barrel `hooks/api/index.ts` for backward import compatibility. Mechanical refactor; no behavior change.

### 5. **Hand-rolled `lib/types.ts` (848 LOC) duplicates backend Pydantic** — SEV: MEDIUM
`package.json:10` already has the script: `openapi-typescript http://localhost:8000/openapi.json -o src/lib/openapi-types.ts`, and `openapi-typescript ^7.4.4` is in devDeps (`package.json:53`). The output is just never generated/committed. Manual sync today means every backend Pydantic edit risks silent type drift (6 imports per `grep`).
**Proposal**: Add `pnpm types` to pre-commit / CI. Generate `openapi-types.ts`, expose curated re-exports from `lib/types.ts` (`type AccuracyGridRow = components['schemas']['AccuracyGridRow']`). Keeps the existing public surface for pages while making backend the source of truth. Zero backend change.

### 6. **Page-level state inconsistently in URL** — SEV: MEDIUM
Some pages do it right: `Trades.tsx:33` (`useSearchParams`), `Theses.tsx:29`. Many don't: `RxFinance.tsx` table sort, `Opportunities.tsx` filters, `AnalysisJobs.tsx` pagination — all live in React state and reset on back-button. Breaks deep-linking and the "share-link with a teammate" workflow (even if "team" is one operator using two devices). Inside tab shells the `tab` slug IS in URL via `useParams`, which is good — but secondary filters aren't.
**Proposal**: Adopt `useSearchParams` for all operator-visible filter/sort state. No new dep. Wrap in a `useUrlState<T>(key, default)` helper in `hooks/use-url-state.ts` to make adoption frictionless.

### 7. **Detail page pattern hand-rolled** — SEV: LOW-MED
`RxFinanceDetail.tsx`, `AnalysisJobDetail.tsx:190`, `TickerHub.tsx:249` all render "back link + breadcrumb + heading + body card stack" independently. `PageHeader` exists in `common/` but the back-link + scroll-restore aren't packaged with it.
**Proposed primitive**: `components/common/DetailLayout.tsx { backTo, backLabel, title, subtitle, children }`. ~60 LOC, replaces three ~25-LOC duplications.

### 8. **`App.tsx` routing has legacy-redirect noise + duplicated `<Suspense>` boilerplate** — SEV: LOW
`App.tsx:55-128` has 11 routes each wrapped in identical `<Suspense fallback={<Skeleton className="h-40 w-full" />}>`. Legacy redirects (`App.tsx:131-164`) are ~30 lines of `<Navigate>` mixed with current routes — hurts scannability. Total 186 LOC is *fine*, but a `<LazyRoute>` helper and a `routes/legacy.tsx` extraction would drop App.tsx to ~80 LOC of current-only routes.
**Proposal**: Extract `routes/legacy-redirects.tsx` (the three `Legacy*Redirect` helpers + Navigate routes), and a `<LazyRoute element={() => import('./pages/Foo')} />` wrapper. Net deletion ~50 LOC.

### 9. **No layout primitives — raw `space-y-*` / `grid-cols-*` everywhere** — SEV: LOW
Every page opens with `<div className="space-y-4|6">`. Two-column layouts inside `RxFinanceDetail.tsx`, `TickerHub.tsx`, `Dashboard.tsx` all re-spell `grid grid-cols-1 md:grid-cols-2 gap-4`.
**Cautious proposal**: `components/common/{Stack,Grid,Container}.tsx`. **Risk of over-abstraction** — Tailwind utility classes are not actually verbose, and adding a Stack wrapper hurts grep-ability ("where is this gap coming from?"). Recommend **defer** unless a future visual-density pass needs to flip default gaps globally. Mark as "watch, don't extract yet".

### 10. **Form pattern split between modal / inline / Dialog** — SEV: LOW
`TradeForm` in `Trades.tsx:45` is a modal (own state-managed editing). `RxFinanceDetail` disposition uses inline. `components/ui/dialog.tsx` exists but not all forms use it. No shared form-state convention (no react-hook-form, no zod resolver).
**Cautious proposal**: For operator-only single-user app, this inconsistency is mostly cosmetic. **Defer**. If we add ≥2 more forms, adopt `react-hook-form + zod` and a `Form` shell primitive at that point. Premature today.

---

## Concrete extract-list (do these)

| New file | Replaces | Net LOC |
| :--- | :--- | :--- |
| `components/common/DriftBar.tsx` | 4 inline copies | −50 |
| `components/common/TabbedShell.tsx` | 7 hand-rolled tab shells | −300 |
| `components/common/DataTable.tsx` | 5–6 hand-rolled tables | −400 |
| `components/common/DetailLayout.tsx` | 3 hand-rolled back-link patterns | −50 |
| `hooks/api/{domain}.ts` split + barrel | `hooks/use-api.ts` monolith | 0 (organizational) |
| `hooks/use-url-state.ts` | inconsistent `useState` filters | small + |
| `lib/openapi-types.ts` (generated) + `lib/types.ts` curated re-exports | manual sync risk | 0 net, removes drift class |
| `routes/legacy-redirects.tsx` + `<LazyRoute>` | inline `App.tsx` noise | −50 |

**Total estimated net deletion: ~800 LOC, zero behavior change, all changes inside `frontend/src/`.**

---

## Don't touch (working well)

- **Sidebar nav grouping** (`Layout.tsx:55-90`) — Today/Decide/Think/Admin/Docs IA is clean, group-collapse persists per-key in localStorage (`Layout.tsx:171-189`), auto-expands on child-route activation. Don't refactor.
- **Backend toggle + health banner** (`Layout.tsx:15-38`) — single source of truth for laptop/railway switching with graceful degraded UX. Leave alone.
- **shadcn `ui/` primitives** — small, focused, idiomatic. The 20 files at `components/ui/` are the right level of abstraction.
- **TanStack Query usage** — query-key conventions and `invalidateQueries` patterns inside `use-api.ts` are correct, just need geographic re-org not behavior change.
- **Lazy-load policy** in `App.tsx:14-45` — markdown / lightweight-charts / research deferred correctly. The pattern itself is fine; just extract the boilerplate.
- **`common/{PageHeader, EmptyState, LoadingStates, HoverTooltip, InfoBubble}`** — already factored; expand this folder, don't replace it.

---

## Risk assessment

| Proposal | Risk | Verdict |
| :--- | :--- | :--- |
| DriftBar / DetailLayout / DataTable / TabbedShell extraction | Low — pure mechanical refactor, visual parity testable | **Net-clearly-good** |
| `use-api.ts` split | Low — barrel preserves imports | **Net-clearly-good** |
| `openapi-typescript` adoption | Low — re-export shim isolates pages from generated names; CI catches drift | **Net-clearly-good** |
| `useUrlState` helper + migrating filters | Low — opt-in per page | **Net-clearly-good** |
| Layout primitives (Stack/Grid/Container) | Medium — over-abstraction risk, hurts grep, low payoff | **Defer** |
| Form unification (react-hook-form + zod) | Medium — adds dep + concept count for marginal win on a single-operator app | **Defer** until ≥2 more forms |
| Routing extraction (`<LazyRoute>` + legacy file) | Low | **Net-clearly-good but low priority** |

---

## Summary

The frontend's strongest move is **factoring the four primitives — `DriftBar`, `TabbedShell`, `DataTable`, `DetailLayout` — and splitting `use-api.ts` per domain**. These four cover ~70% of the surface duplication and shave ~800 LOC without touching backend, routing semantics, or visual design. The riskiest temptation is layout primitives and form frameworks; both are premature for a single-operator app and would add concept count for marginal payoff. The highest-leverage type-safety win is finally running the existing `openapi-typescript` script — the devDep is already paid for.

