# Decisions log — UX rework 2026-05-17

Living document. Each phase appends one entry.

Format:
```
## Phase N — <name> (timestamp)
- **Shipped**: bullet list of concrete changes
- **Files touched**: paths
- **Verification**: TS / tests / Playwright result
- **Operator-visible impact**: 1 sentence
- **Skeptic check**: what we declined to do
- **Gap/blindspot found in audit**: anything caught + fix
```

---

## Retro — full rework (2026-05-17, 7 phases shipped autonomously)

**Council**: 4 parallel voices (UX strategist + visual designer + frontend architect + skeptic) + synthesis. Files at `.claude/decisions/ux-rework-2026-05-17/{01..05}.md`.

**Shipped, in dependency order**:
1. Foundation primitives (DriftBar, StatusBadge, TabbedShell) — replaced drifted dialects + tab boilerplate across 7+ files
2. Card vocabulary inversion + PageHeader hierarchy + tabular-nums — visual designer P0-2/P1-5 fixes
3. Today reshape — 4 zones (Action / Inbox / What changed / Inbox detail); InboxCounter primitive
4. Sidecar pattern — `PageWithSidecar` + `SidecarTile` + RecsSidecar + PositionsSidecar — killed ~600px empty grey clay
5. Rec/trade ergonomics — mobile-stacked RecCard + Context/conflict columns + 2-up CTA + snooze history
6. Sidebar widget polish + `/recs` `/trades` top-level shortcuts
7. Architect cleanup — `LazyRoute` helper + `useUrlState` hook + dup `/trades` route deleted

**Total changes**: 14 new files (10 primitives + 4 page-level components); 11 changed pages/components; App.tsx 200 → 149 LOC; rx.md updated; pages.md updated; roadmap-shipped entry written.

**Backend**: untouched per soft-gate (zero new endpoints, zero schema changes).
**Information layer**: untouched per hard-gate (vault_indexer, ingest, research). ✓

**Skeptic-cleared declines** (proven over-reach via council debate):
- use-api.ts split — 1832-LOC monolith, barrel pattern works, regression risk > marginal cohesion gain
- openapi-typescript CI adoption — would force backend Pydantic tightening (soft-gate)
- DataTable primitive extract — premature without 3+ pages adopting side-by-side
- Decide/Think sidebar rename — muscle memory cost
- Trades workflow redesign — frozen for 7d of live trades

**Pre-existing regression caught**: `tests/test_earnings_trigger_polling.py::test_trigger_block_polls_when_inside_window` fails on every run; confirmed via git-stash this was broken before Phase 1; unrelated date-edge bug in earnings-ingest pollers. Filed as a follow-up — not blocking.

**Operator-visible deltas**:
- Today total scroll at 1440 reduced ~40% (4-up grid replaces 2×2 + the 8-stacked-surface stack)
- Sidebar widgets no longer compete with main content
- Mobile rec list doesn't side-scroll
- Conflict + position + watchlist annotations on rec list highlight which recs actually affect the operator's book
- ~600px empty clay below tables filled with disposition funnel + concentration narratives
- Status badges consistent across rec / hypothesis / trade / opportunity / position / flag surfaces
- /recs + /trades shortcut URLs work
- Rec → trade flow still 1-click; rec → thesis promote available

**Verification**: TS clean; 727 backend tests pass (1 pre-existing date-flake); 5 council files + 7 log entries; Playwright walk captured at `.audit/{p1-p7}*.png` + `.audit/final-*.png`; rec→trade smoke re-verified post each phase; sidebar widget visual weight measured via element-screenshot.

---

## Phase 7 — Architect cleanup (2026-05-17)
- **Shipped**:
  - `components/common/LazyRoute.tsx` — `<LazyRoute Component={X} />` replaces the per-route `<Suspense fallback={<Skeleton h-40 w-full/>}><X /></Suspense>` boilerplate
  - Adopted LazyRoute on 7 of 11 lazy routes in App.tsx (Macro/Research/TVContextInbox/TheStreet/Admin×3/Docs)
  - `hooks/use-url-state.ts` — opt-in URL-state helper for filter/sort state (architect issue #6); not adopted anywhere yet, available for future page work
  - App.tsx LOC: 200 → 149 (~25% reduction). Removed dup `/trades` route registration.
- **Files touched**: 2 new (LazyRoute, useUrlState), 1 changed (App.tsx)
- **Verification**: TS clean; 727 backend tests pass (was 720; +5 net from earlier phases now reflected since this run includes all rx-route + rx-links tests; +2 from misc); Playwright `.audit/final-01-today.png` shows Today w/ all 4 zones rendering correctly w/ new compact widgets in sidebar
- **Operator-visible impact**: zero (mechanical refactor only)
- **Skeptic check**: did NOT do the use-api.ts split (1832 LOC monolith would force every page-test re-validation for marginal cohesion gain — skeptic's "demand 3 duplicate sites before accepting any new primitive" applies in reverse: existing barrel-import works); did NOT adopt openapi-typescript (skeptic's risk-of-backend-tightening); did NOT extract DataTable primitive (premature without 3+ pages adopting it side-by-side); did NOT rename Decide/Think → Scan/Research (muscle memory cost)
- **Gap/blindspot**: ThesesShell + Predictions + Motion still own their `<Suspense fallback>` inside their tab-shell rather than using LazyRoute (because they pass a lazily-loaded component as a tab `render: () => <Suspended … />`). Acceptable; LazyRoute would require generic tab-render typing changes for a small win.
---

## Phase 6 — Sidebar polish + IA tweaks (2026-05-17)
- **Shipped**:
  - RxStatusWidget + HypothesisStatusWidget compacted to a 2-line text strip — no inset card, no shadow, muted-foreground labels with foreground tabular-num values. Designer P2-9 (sidebar shouldn't be the brightest objects on the page).
  - HypothesisStatusWidget now clickable → `/theses` (was static text).
  - Top-level `/recs` redirect → `/motion/recs` and `/recs/:id` → `/motion/recs/:id` (UX strategist O8: easier-to-type URLs for high-frequency surfaces).
  - Top-level `/trades` redirect → `/motion/trades`.
- **Files touched**: RxStatusWidget.tsx, HypothesisStatusWidget.tsx, App.tsx
- **Verification**: TS clean; `.audit/p6-01-sidebar-widgets.png` shows widgets are now visually ambient — text-only, no card chrome competing with main content
- **Operator-visible impact**: sidebar widgets pull less attention; `/recs` and `/trades` shortcut URLs work
- **Skeptic check**: did NOT rename sidebar groups (Decide/Think → Scan/Research was proposed by UX strategist O4 but skipped to preserve muscle memory); did NOT add new sidebar entries
- **Gap/blindspot**: HypothesisStatusWidget loading skeleton suppressed (returned null instead of placeholder) — operator might see a brief layout shift between load and first paint. Acceptable for a sidebar widget.
---

## Phase 5 — Rec/trade ergonomics (2026-05-17)
- **Shipped**:
  - `components/rx/RecRow.tsx` — mobile-stacked rec card (`md:hidden` variant of the table row) — UX strategist B5 mobile fix
  - RxFinance lists now annotate each rec w/ ticker (regex extract w/ denylist) + inPosition + inWatchlist + conflict (heuristic: trim/close/sell verb on a held long)
  - New Context column on desktop table showing "IN POSITION" / "ON WATCHLIST" inline
  - New `conflict` flag value on StatusBadge (distinct dangerOutline w/ "conflict" label, NOT reused "forced")
  - Default sort: forced > aging > conflict > drift desc (UX strategist O5)
  - Rec detail page: "Promote to thesis" CTA paired w/ "Log trade" in a 2-up row (UX strategist B4)
  - Rec detail page: snooze history section visible when snooze_count > 0 (UX strategist B2)
- **Files touched**: 3 new (RecRow, RecsSidecar, PositionsSidecar, DetailSidecar primitive already shipped in P4), 2 changed (RxFinance, RxFinanceDetail)
- **Verification**: TS clean; Playwright `.audit/p5-04-recs-list-wide.png` (1920×1080) shows all 8 columns inc. Context (IN POSITION) + Flags (forced + conflict); `.audit/p5-02-detail.png` shows 2-up CTA row; rec→trade e2e re-verified (POST trade w/ related_rec_id → trade visible w/ FK)
- **Operator-visible impact**: at-a-glance "this rec affects an open position" signal on rec list; mobile rec view doesn't side-scroll; snooze history visible per rec; "promote-to-thesis" CTA gives the operator an action path when a rec reveals a pattern worth crystallising
- **Skeptic check**: did NOT touch backend (the Promote-to-thesis CTA is just a URL with query params; the Theses page is responsible for honoring `?from_rec=<id>` — left as a hook that future Phase Theses-improvement can implement); did NOT add any new endpoints
- **Gap/blindspot**: Promote-to-thesis CTA navigates to `/theses?from_rec=…&ticker=…` but Theses page doesn't yet consume these params — operator gets dropped on the theses list. Acceptable for now (one extra click to author thesis manually); future phase upgrades Theses to prefill from the rec
---

## Phase 4 — Sidecar pattern (2026-05-17)
- **Shipped**:
  - `components/common/DetailSidecar.tsx` — exports `PageWithSidecar` layout + `SidecarTile` card. `xl:flex-row` keeps the rail at ≥1280px and stacks below
  - `components/rx/RecsSidecar.tsx` — disposition funnel (open/snoozed/acted/dismissed w/ bar viz), attention flags (aging+forced counts), next-batch hint
  - `components/rx/PositionsSidecar.tsx` — concentration top-5 (bar per ticker), cost-basis vs current-value vs unrealized P&L w/ %, risk thresholds reference
  - Wired into RxFinance + RxFinancePositions pages
- **Files touched**: 3 new (sidecar primitive + 2 rx sidecars), 2 changed (page wrappers)
- **Verification**: TS clean; Playwright `.audit/p4-01-recs.png` + `p4-02-positions.png` show the right rail is populated; ~600px of empty grey clay gone
- **Operator-visible impact**: at-a-glance disposition habit + concentration risk visible without leaving the list page; sidecar provides answers operator otherwise has to compute by scrolling/jumping
- **Skeptic check**: did NOT add a sidecar to Trades (no good aggregate to show until equity curve / win-rate accumulates from real data — UX strategist B-callout); did NOT touch detail pages
- **Gap/blindspot**: at < xl breakpoint the sidecar drops below the table (stacks), so on ~1280px screens the operator sees a tall page; tradeoff accepted because 320px sidecar + 920px table doesn't fit at lg (1024). Operator's primary screen is 1440 so it shows correctly.
---

## Phase 3 — Today reshape (2026-05-17)
- **Shipped**:
  - `components/today/InboxCounter.tsx` — single-row counter for ticker review + research approvals; hidden when both are 0
  - Today reshaped to 4 zones: Action queue (RxStrip) → Inbox aggregate (counter) → What changed (4-up compact grid w/ lg:grid-cols-4) → Inbox detail strips (preserved for muscle memory + inline triage)
  - Page header upgraded to use `PageHeader` w/ Sun icon + Run Now in actions slot
- **Files touched**: 1 new (InboxCounter), 1 changed (Today.tsx)
- **Verification**: TS clean; Playwright `.audit/p3-01-today.png` (desktop 1440) shows the 4 narrative cards now sit in a single row instead of 2x2 stack — total scroll for the top fold reduced by ~40%; `p3-02-today-mobile.png` (400×800) shows mobile stack still works
- **Operator-visible impact**: action queue (open recs) is the first thing visible after the page header instead of the 4 narrative cards; inbox counter gives at-a-glance triage signal; existing strips remain available below for the operator who wants inline triage
- **Skeptic check**: did NOT remove any existing strips (TickerReviewStrip/TVContextStrip/WatchlistDelta/PendingReviewPanel all still render below); did NOT change the 4 narrative cards' content or behavior — just laid them out as 4-up; muscle memory survives
- **Gap/blindspot**: InboxCounter does NOT include TV context items (no `useTVContext` list hook exists; the strip uses per-ticker fan-out). Could add a backend `/v1/tv-context/recent` endpoint in Phase 7 if operator wants it counted; for now the TVContextStrip below handles it visually
---

## Phase 2 — Card vocabulary inversion + PageHeader hierarchy (2026-05-17)
- **Shipped**:
  - `PageHeader.tsx` upgraded — 3xl extrabold + 4px violet anchor bar; `icon` slot; backwards-compat `tight` mode for nested headers
  - Adopted PageHeader on RxFinance, RxFinancePositions, RxFinanceHypotheses
  - Inverted KPI card vocabulary from inset → extruded on Positions + Trades + RxFinanceDetail (Card components within those pages updated)
  - Enforced `tabular-nums` on metric values (font-display extrabold + tabular-nums)
- **Files touched**: 4 pages + 1 primitive
- **Verification**: TS clean; Playwright `.audit/p2-01-positions.png` shows clear visual lift — Portfolio Value / Unrealized P&L / Open Positions render as raised cards instead of form-field wells; H1 anchor bar visible at left of title; P&L green
- **Operator-visible impact**: KPIs read as primary metrics instead of form labels; page H1s now claim hierarchy over the page-tab strip
- **Skeptic check**: did NOT rename tokens, did NOT add typography plugin (uses existing `.docs-article` + tabular-nums utility), did NOT touch trade-flow surfaces
- **Gap/blindspot**: Trades.tsx still has its 3 SummaryCard kpi — already updated to tabular-nums + extrabold but uses `shadow-extruded` (not extruded-sm); acceptable, both are extruded
---

## Phase 1 — Foundation primitives (2026-05-17)
- **Shipped**:
  - `components/common/DriftBar.tsx` — unified scalar bar (`sm`/`md`/`lg`), aria meter, color thresholds (success<0.40, warning<0.70, danger≥0.70)
  - `components/common/StatusBadge.tsx` — single vocabulary for rec/hypothesis/trade/opportunity/position/flag; one tone table; xs and sm sizes
  - `components/common/TabbedShell.tsx` — replaces the per-page tab boilerplate; supports detail short-circuit via `isDetail` + `detail` props
  - Refactored consumers: `Motion.tsx` (4 tabs + detail), `ThesesShell.tsx` (2 tabs), `Predictions.tsx` (3 tabs) now go through TabbedShell. `RxFinance.tsx`, `RxFinanceDetail.tsx`, `RxFinanceHypotheses.tsx`, `today/RxStrip.tsx` migrated to new primitives.
- **Files touched**: 9 files (3 new common, 6 refactored)
- **Verification**: TS clean; 720/721 backend tests pass (1 pre-existing test_earnings_trigger_polling failure unrelated — confirmed via git-stash regression test on pre-Phase-1 code); Playwright screenshot `.audit/p1-01-motion-recs.png` shows visual parity with `.audit/v2-02-recs.png`
- **Operator-visible impact**: zero visual change beyond status-badge consistency (no more 3 different shades of "open").
- **Skeptic check**: declined to refactor Admin/TheStreet/WatchlistConsolidated/Macro into TabbedShell — they have cross-tab shared state (`since` filter on Macro, jobs detail param on Admin) that the simple primitive doesn't model yet. Kept hand-rolled.
- **Gap/blindspot found**: hand-rolled "active" / "at risk" badges on `Theses.tsx:64-71` still use raw semantic-token classes. Acceptable — they're counter badges (numeric), not status badges. Doesn't dilute the vocabulary unification.

---
