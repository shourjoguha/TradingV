# Synthesis + Phased Plan — UX rework 2026-05-17

## Council convergence

All 4 voices agree:
- **Primitives extraction is overdue** (architect HIGH × 4 + designer says drift is real). DriftBar duplicated 4×; tab shells hand-rolled 7×; status badges 3 different dialects.
- **Empty grey clay below tables is the biggest aesthetic problem** (designer P0-3, UX strategist B5, architect implicit).
- **Operator's rec→trade→position loop must not break** (skeptic explicit, UX strategist O8 implicit, designer notes mobile risk).

Divergence:
- **UX strategist** wants aggressive IA reshape (split Motion, promote Trades/Recs to sidebar).
- **Skeptic** wants freeze on rx workflow until 1 week of live trades.
- **Visual designer** wants Today reimagined as morning briefing strip.

## Resolution (per operator brief: "do not be afraid to reimagine")

Operator's mandate over-rides the skeptic's freeze on workflow surfaces — but the skeptic's points on backend coupling, token rename, and "don't break working stuff" are respected. Specifically:

- **Reimagine permitted**: Today, sidebar, /motion shell, /recs default sort, status badge vocabulary, card physics
- **Don't touch**: information layer (hard gate), backend Pydantic shapes (soft gate), shadcn primitive contracts (skeptic), neumorphic tokens (skeptic — they were just re-validated)
- **Workflow continuity is the success criterion**: at no phase should the rec→trade flow regress. Verify via Playwright between phases.

## Phased plan (7 phases, each ships → audits → docs)

### Phase 1 — Foundation primitives (low risk, multiplier)
Extract three primitives + refactor consumers. Pure mechanical — no UX change beyond consistency.

- `components/common/DriftBar.tsx` — 1 implementation replaces 4 (RxStrip, RxFinance, RxFinanceDetail, Trades).
- `components/common/StatusBadge.tsx` — unified vocabulary (designer §4). Replaces dialects in RxFinance, Theses, Trades, Opportunities.
- `components/common/TabbedShell.tsx` — extracts the 7-page boilerplate (Motion, Predictions, Macro, Admin, TheStreet, ThesesShell, WatchlistConsolidated).

**Exit gate**: TS clean, all pages visually unchanged via screenshot diff, 721 tests still pass.

### Phase 2 — Card vocabulary + page header hierarchy (designer P0-2, P1-5)
- Flip KPI cards inset → extruded on Positions, Trades, RxFinanceDetail.
- New `components/common/PageHeader.tsx` with 4px violet anchor bar + tighter sub-text.
- Tabular nums enforced via `.num` utility (designer P1-4).
- Apply across all top-level pages.

**Exit gate**: visual diff captured for Today, Recs, Positions, Trades, Theses, Macro, Research.

### Phase 3 — Today reshape (UX O1 — collapse 8 surfaces to 3 zones)
- New `components/today/MorningBriefing.tsx` merges DriftCard + FreshSignalsCard + WatchlistDelta into one consolidated card.
- New `components/today/InboxAggregate.tsx` merges TVContextStrip + TickerReviewStrip + PendingReviewPanel into one "Inbox" surface.
- Keep RxStrip as Zone 1 (action queue, already shipped).
- MarketMood demoted to a 1-line header under page title.
- Today.tsx becomes: header (with last-tick indicator) → RxStrip (Action) → MorningBriefing (What changed) → InboxAggregate (Backlog) → footer (legacy link).

**Exit gate**: total scroll <1 viewport at 1440×900; mobile single-column readable.

### Phase 4 — Sidecar pattern (designer P0-3 — kill the empty grey clay)
- New `components/common/DetailSidecar.tsx` — 320–360px right rail.
- Mount on /motion/recs (rec funnel histogram + "next rec drops in" countdown), /motion/positions (concentration + thesis-match sparkline), /motion/trades (30d P&L sparkline + win-rate gauge — these will populate over time).
- Empty-state behavior: card shows hint + CTA, never blank.

**Exit gate**: no >300px vertical empty space on any list page at 1440×900.

### Phase 5 — Rec/trade ergonomics (skeptic-cleared scope)
- Snooze history mini-section on rec detail (UX B2).
- "Promote to thesis" CTA on rec detail (UX B4 — UI only; backend creates hypothesis via existing POST /v1/hypotheses).
- Mobile-stacked card list for rec/trade tables (UX B5).
- "Conflicts" + "In Watchlist" columns on /motion/recs (client-side compute from existing queries).
- Re-rank default sort: forced > aging > conflicts > drift.

**Exit gate**: rec→trade→position e2e smoke still works; mobile screenshot captured.

### Phase 6 — Sidebar refinement + IA tweaks
- Tighten sidebar widget styling (designer P2-9 — drop shadow, reduce visual weight).
- Add `/trades`, `/recs` top-level redirects (UX O8 — preserve muscle memory + provide direct URL).
- Sidebar widget for "open recs" gains tiny weekly sparkline.
- "Decide" → "Scan", "Think" → "Research" rename (UX O4) — sidebar labels only, no route change.

**Exit gate**: sidebar widget visual weight ≤ main content; deep-links work.

### Phase 7 — Architect cleanup (defer if behind)
- Split `hooks/use-api.ts` by domain (`hooks/api/{rx,research,...}.ts` + barrel).
- DataTable primitive extraction (if pattern survives Phase 1-4 use).
- DetailLayout primitive.
- `openapi-typescript` CI adoption (skip if backend Pydantic stability changes per skeptic).
- Routing extract (legacy redirects → separate file + `LazyRoute` helper).

**Exit gate**: bundle size unchanged or smaller; LOC delta ~-800.

## Out of scope (skeptic-cleared, won't ship this cycle)

- Token rename / "design system v2"
- Dark mode
- Command palette
- Form framework adoption (react-hook-form + zod)
- Illustrated empty states
- Animation/motion polish on rx surfaces
- Theses-Health column removal (already shipped v1.x.1-d)

## Verification protocol (each phase)

1. Touch code → TS check
2. Backend tests still pass (`pytest --ignore=tests/test_vault_indexer*`)
3. Live Playwright walk: navigate Today → /motion/recs → /motion/recs/:id → /motion/trades → /motion/positions → /theses → /theses/health → Inbox/TVContext, screenshot each, diff against prior phase
4. Append phase retro to `/.claude/decisions/ux-rework-2026-05-17/log.md`
5. Update `.claude/modules/rx.md` + `.claude/frontend/pages.md` where relevant
6. Verify rec→trade smoke (seed rec → open detail → "Log trade" CTA → form prefilled → POST → trade with rec linkage visible)

## Decision log file

All decisions logged at `.claude/decisions/ux-rework-2026-05-17/log.md`. Each phase appends:
- Decision summary
- Files touched
- Verification result
- Operator-visible impact (1 sentence)
- Skeptic check (what did we decline to do)
