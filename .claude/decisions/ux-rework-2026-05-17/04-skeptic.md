# 04 — Skeptic

_Written before peer files (01/02/03) exist. Update on second pass once they land._

The operator starts logging real trades **tomorrow**. The single load-bearing question for this council is: *does any proposal here risk the rec → trade → position loop being broken on day 1?* If yes, defer it. If no, prove it ships <2 days of churn.

## Leave alone (do not touch in this rework)

- **Neumorphic design system + `ui-components.md` compositions.** 15 enhancements just landed in v1.x.1-d. The Pattern A vs B tab/chip decision matrix is exactly the kind of doc visual designers love to "modernize." Don't. The drift incidents that motivated it haven't stopped being a risk.
- **`Today.tsx` 2×2 narrative grid.** Shipped 2026-05-13. The role-descriptions-survive-empty-state pattern is deliberate and correct. Operator has muscle memory for the layout already.
- **`RxFinance.tsx` table.** It's 125 lines, scans cleanly, and IS the disposition surface for the locked rx routing rule. The aging/forced badges are working signals. Any redesign here directly threatens tomorrow's trading workflow. **Hard freeze through at least 7 days of live trades.**
- **`TickerHub.tsx` 6-section join.** Phase 2 IA reorg's centerpiece. Information-dense by design — not a candidate for "cleanup."
- **Sidebar nav groups (Today / Decide / Think / Admin / Docs).** Recent IA reorg, operator-learned. Re-grouping costs muscle memory for no clear win.
- **`BackendToggle`, `HypothesisStatusWidget`, the docs viewer.** Working, low-traffic, not blocking anything.

## Probably yes — with caveats

- **Visual polish to non-rx pages** (Macro, Predictions, Accuracy heatmap). Safe sandbox: low workflow risk, no backend coupling. Cap at *additive* changes — no token renames, no shadow-token deletions.
- **`Trades.tsx` ergonomic improvements** (close-trade modal speed, prefill-from-opp clarity). High value because it activates tomorrow. **Constraint:** ship behind a feature flag OR ship Monday after first weekend of actual trades, never both at once with rx changes.
- **Empty-state copy upgrades.** Cheap. But only on pages where data WILL stay sparse (Docs stub, hypothesis widget). Skip pages that will populate in 2 weeks — wasted work.
- **`use-api.ts` hook consolidation** if the architect proposes it. Acceptable only if zero changes to query keys (cache invalidation breaks silently).

## Reject (or shoot down hard)

- **Any "design system v2" / token rename / shadow-token refactor.** v1.x.1-d just touched the rx layer with current tokens. A rename means re-validating every page. 100% cost, ~0% operator-visible benefit.
- **Component-library extraction / new primitives "for consistency."** 20 primitives already shipped, all used. New ones die in `ui/` per the existing doc's own warning. If the visual designer proposes a `<StatCard>` or `<SectionHeader>` abstraction, demand 3 existing duplicate sites first.
- **Dark mode.** Explicitly anti-patterned in `ui-components.md`. If proposed, reject on sight.
- **Rx workflow redesigns** (modal flows, card layouts, status state machine UI). The status machine is the *backend* contract. Touching the UI here either (a) doesn't touch backend and is cosmetic, or (b) requires backend changes — soft-gate violation.
- **Pretty empty states with illustrations.** Operator has data flowing in 2 weeks. Illustration work obsoletes itself.
- **Cross-page "command palette" / global search.** Classic council scope creep. 29 pages don't need one operator to keyboard-jump; the sidebar works.
- **Animation/motion polish on rx surfaces.** Adds latency perception and visual noise during the most cognitively-loaded moment (deciding whether to act on a rec).

## Hidden costs the proposers will undersell

- **"Just a Tailwind token swap"** = touches every page, requires per-page visual diff. Budget 3× whatever they say.
- **"Extracted into a shared component"** = new file to maintain, new failure surface, new test target. The 200-400 line file budget exists for a reason.
- **"Lazy-loaded a section"** — already done for the heavy pages (Admin, Macro, Research, TVContextInbox, Watchlists, Docs). Additional lazy boundaries hit diminishing returns and complicate error boundaries.
- **"Consolidated `WatchlistConsolidated` further"** — that page is already a Phase 3 consolidation. Re-consolidating risks the redirect chain (`/roster`, `/watchlists/:boardId` → `#boards`). Operator deep-links here.
- **"Strict TypeScript / schema validation at fetch boundary"** — sounds free, isn't. Will surface backend response shapes that are loose-by-design, forcing backend tightening = soft-gate breach.

## Phasing — what ships, what waits

**Week 1 (this week — trades start tomorrow):**
- FREEZE all rx pages and `Trades.tsx`.
- Allowed: copy edits, accessibility fixes (aria labels, focus rings), one-off bug fixes flagged in v1.x.1-d retro.

**Week 2 (after 5 days of live trading data):**
- Polish `Trades.tsx` ergonomics if and only if the operator names a specific pain point from actual use.
- Visual polish on Macro / Accuracy / Predictions (no token churn).

**Week 3+:**
- Consider any structural proposal from agents 01/02/03 that survived this skeptic pass.

The default answer this week is **no**. Make proposers prove the operator asked for it or that the current state actively bleeds.

---

## Update after reading peer files

_TBD — peer files (01/02/03) not yet present at write time. On second pass, append accept/reject deltas per proposal here._
