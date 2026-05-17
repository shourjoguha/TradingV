# UX Strategist — TradingV Frontend Reshape

**Author**: UX Strategist voice (council 1/4) · **Date**: 2026-05-17 · **Scope**: frontend only (`frontend/src/`); no info-layer changes.
**Trigger**: Operator logs first real trade tomorrow; workflow A→D becomes the load-bearing path.

---

## Premise: who is this app for, today?

One operator. Eight workflows ranked by frequency: **A** morning glance → **B** disposition open rec → **C** log trade → **D** check positions → **E** audit thesis → **F** run research → **G** manage watchlist → **H** admin.

Of those, A–D fire daily. E–F fire weekly. G fires when curiosity strikes. H fires when something breaks. The current IA was built incrementally over multiple phases and now **distributes daily work across three top-level groups** (Today, Decide, Think) plus a sidebar widget pair. The cost is decision latency every morning: "which surface tells me what changed?"

---

## Observations

### O1 — Today.tsx is no longer glanceable. **[P0, M, low risk]**
`frontend/src/pages/Today.tsx:37–85` renders, in order: a 2×2 narrative grid (DriftCard / FreshSignalsCard / ResearchCuriousCard / MarketMoodCard) → RxStrip → TickerReviewStrip → TVContextStrip → WatchlistDelta → PendingReviewPanel → legacy-dashboard link. That's **eight discrete surfaces** stacked on the morning page. The original `space-y-6` (line 38) suggests a calm scan; the actual scroll length is ~3 viewports. The page's own docstring (lines 27–32) brags about solving cognitive overload — but solving it for *PendingReviewPanel* while quietly re-creating it page-wide.

**Reshape**: collapse Today to **three zones**: (1) Action queue (open recs + forced/aging at top — what needs *me* this morning); (2) What changed overnight (drift + fresh signals + watchlist delta merged into a single "Signals since last open" card); (3) Mood/context (market mood + TV context strip as a thin sticky footer, not full cards). Kill MarketMoodCard as a full card — demote to a one-liner.

### O2 — "Open recommendations" is surfaced in **three places**, none authoritative. **[P0, S, low risk]**
RxStatusWidget (sidebar, `RxStatusWidget.tsx:8–44`), RxStrip (Today, `RxStrip.tsx:49–147`), and the `/motion/recs` table (`RxFinance.tsx:48–125`) all show the same eligible-recs view filtered by `status='open' OR (snoozed && auto_revived)`. The widget shows count, the strip shows top-3 by drift, the table shows all 200. Three reads, three slightly different summaries, **no inbox-zero affordance** — nothing tells the operator "you're clear." The widget and strip both auto-hide when empty (good!), but the operator has no positive confirmation, just absence.

**Reshape**: keep the sidebar widget as the persistent counter. Inline the strip's top-3 into Today's Zone 1 (above). Add a one-line "All recs dispositioned ✓ — next batch when /rx-finance runs" state when count is 0. Show it on Today only.

### O3 — Motion's 4 tabs conflate four different temporalities. **[P1, M, medium risk]**
`Motion.tsx:20–26` groups Opportunities (future), Trades (past), Positions (present), Recommendations (prescribed action). The doc-comment (lines 29–32) sells "decide → act → hold → reflect" as one mental model. It isn't. **Opportunities are model output; Trades are journal; Positions are accounting; Recs are an entirely different generator (Claude Code, not Kronos).** Tab-switching forces context-flip across four data origins. Worse, the rec detail short-circuits the tab shell entirely (lines 43–49), so the IA promise "all four live together" silently breaks the moment you drill in.

**Reshape**: split Motion into **Trade** (positions + trades; one shell, two tabs — the operator's accounting) and **Signals** (opportunities; standalone page). Move Recommendations OUT of Motion entirely into its own top-level `/recs` route, because that's where the *daily* action lives (workflow B) and burying it as Motion's 4th tab is wrong-priority. Today's strip becomes the primary entry; the page is for backlog review.

### O4 — Sidebar groups are organized by metaphor, not by frequency. **[P1, S, low risk]**
`Layout.tsx:55–90` has Today (1 leaf) / Decide (4 children) / Think (4 children) / Admin (collapsed) / Docs. The "Decide vs Think" split is poetic but operationally weak — **Watchlist** lives under Decide, **TV Context** lives under Think, but in the operator's head they're both "things I look at when I have a hunch." Meanwhile **Trades** doesn't appear in the sidebar at all (it's a Motion tab), even though it's a P0 daily workflow starting tomorrow.

**Reshape**: re-cut sidebar by **frequency × intent** — see proposed IA below. Trades earns a top-level entry. "Decide/Think" becomes "Scan/Research."

### O5 — Information scent on `/motion/recs` table is weak. **[P1, S, low risk]**
`RxFinance.tsx:76–122` shows columns: ID | When | Drift | Conf | Status | TLDR | Flags. The operator needs to choose which rec to open. Drift is the loudest visual signal, but **drift is a property of the model, not of the rec's urgency.** A high-drift, low-confidence rec on a ticker I don't hold is less urgent than a low-drift, high-confidence rec that contradicts an open position. The table can't show that — it has no position-overlap or thesis-conflict column.

**Reshape**: add **"Conflicts"** column showing 🔴 if the rec contradicts an open position or active thesis; **"In WL"** column showing if the ticker is on the watchlist. These compute client-side from existing queries. Re-rank default sort to: `forced > aging > conflicts > drift`.

### O6 — Theses → Health tab is structurally hidden. **[P2, S, low risk]**
`ThesesShell.tsx:21–63` adds a "Health" sub-tab. The view shows how many recent recs reference each hypothesis. But the operator's morning glance doesn't surface "thesis X has been referenced in 4 recs this week" — they have to navigate `/theses/health` and choose to look. The HypothesisStatusWidget shows count and at-risk but not engagement velocity.

**Reshape**: surface a "Thesis pulse" sparkline in the sidebar widget (e.g., "3 referenced this week"). Promote the Health view's signal into the at-risk computation: a thesis that hasn't been mentioned in 30d *and* has TTL < 30d ahead is doubly at risk.

### O7 — TVContextInbox + TVContextStrip + TickerReviewStrip are three inboxes for one workflow. **[P2, M, low risk]**
TV Context (sidebar entry) + TVContextStrip (Today) + TickerReviewStrip (Today, unknown-ticker queue from Phase D Commit 2). Three review queues, each with their own "pending count," none of which inbox-zero together. The operator triages by jumping between them.

**Reshape**: merge into a single `/inbox` route with sub-tabs (Chart context | Unknown tickers | Research approvals). Pull all three into one Today card: "Inbox — 4 items waiting." Promotes inbox-zero as a real goal.

### O8 — Trades.tsx is reached via `/motion/trades` not `/trades`. **[P0, S, low risk]**
`Trades.tsx:65–78` is the page the operator opens tomorrow morning to log their first real trade. The URL is buried two levels deep (`/motion/trades`), there's no top-level sidebar entry, and the deep-link from rec detail (`tradeHref` in `RxFinanceDetail.tsx:74`) goes to `/motion/trades?rec=…`. **First-real-use moment + buried surface = friction at exactly the wrong time.**

**Reshape**: promote `/trades` to top-level. Keep `/motion/trades` as a redirect for the deep-link compatibility.

### O9 — No "system mode" indicator. **[P2, S, low risk]**
Today.tsx has a "Run Now" button (line 49) but no indication of whether the scheduler last fired successfully, when, or what it produced. The operator has to navigate to Admin to see scheduler health. The BackendHealthBanner (`Layout.tsx:15–38`) handles backend reachability but not data freshness.

**Reshape**: add a small "Last tick: 2h ago · 3 predictions · 1 alert" footer to Today's header, click-through to admin overview.

---

## Proposed new IA

```
SIDEBAR
─────────────────
Today                ← /                 (P0 daily — morning glance, shrunken)
Recs                 ← /recs             (P0 daily — promoted from motion tab)
Trades               ← /trades           (P0 daily NEW — promoted)
Inbox                ← /inbox            (P1 — TV ctx + ticker review + research approvals)
Scan                 ─ (was: Decide)
  Signals            ← /signals          (was: /motion, opportunities-only)
  Predictions        ← /predictions
  Macro              ← /macro
  Watchlist          ← /watchlist
Research             ─ (was: Think)
  Ask                ← /research
  Theses             ← /theses           (drop Health tab, fold into widget)
  The Street         ← /the-street
Admin                ─ collapsed
Docs                 ← /docs
WIDGETS (sidebar bottom)
  RxStatusWidget       (open recs · forced count)
  HypothesisWidget     (active · at-risk · weekly-pulse NEW)
```

Pages killed/merged:
- Motion shell → split into Signals (opps) + Trades + Positions (Trades tab).
- TVContextInbox + TickerReview pages → Inbox sub-tabs.
- ThesesShell.Health → folded into widget pulse + at-risk math.

---

## "Morning glance" redesign

If forced to pick **3 surfaces** for Today:

1. **Action queue** (rec strip + forced/aging banner). One card. "Here is what needs you in the next 10 minutes." Zero state = explicit "✓ all clear." Click any row → rec detail.
2. **What changed** (drift card + fresh signals + watchlist delta merged into one timeline-style card). One card. "Here is what moved since you last opened the app." Tagged by ticker so the operator scans by symbol, not by surface.
3. **Inbox** (TV context + unknown tickers + research approvals as a single counter). One card. "4 items want your eyes when you have time."

That's three cards. Mood + TVContext footer (collapsed by default, expand on click). Run Now button + last-tick indicator in the header.

Total scroll: <1 viewport.

---

## Blindspots (will bite in 2 weeks)

- **B1 — Rec-to-trade-to-position-to-disposition is uninstrumented**. The operator logs a trade from a rec (`RxFinanceDetail.tsx:74` deep-link), but there's no "did this rec become a winning trade?" backtrace UI. In 2 weeks the operator will have 15 dispositioned recs and no way to scan their per-rec P&L attribution. **Build**: a "rec outcomes" table on `/recs` showing rec → trade(s) → realized P&L. Backend already has the linkage (`useRxLinks`).
- **B2 — "Forced decision" chip is an alarm with no audit trail.** Operator will see "forced" badges and click-snooze through them once the novelty wears off. No history view of "you've snoozed this rec 3 times in 2 weeks." **Build**: snooze history in rec detail; auto-escalate at snooze_count ≥ 3 instead of 2.
- **B3 — Positions tab inside Motion will lose visibility once trades start logging.** Operator will live in `/trades` and never see `/motion/positions`. Currently they're siblings; after split, Positions needs to be a Trades sub-tab (so it's seen in the same workflow), not a sibling route.
- **B4 — Theses page has no "I want to author a new thesis from this rec" affordance.** The operator's mental model: rec arrives → "huh, this is a real pattern" → wants to crystallize it as a thesis. No UI path. **Build**: "Promote to thesis" button on rec detail.
- **B5 — Mobile is silently broken for the most important workflow.** RxFinance table (`RxFinance.tsx:75`) uses `overflow-x-auto` — on phone the rec table side-scrolls. Operator opens phone at 8am, can't see flags column without scrolling. The morning glance is mobile-critical. **Build**: stacked card list for `<md` breakpoint instead of horizontal scroll.
- **B6 — No "what did I do yesterday" recap.** Workflows A and E both implicitly want this. The operator opens at 8am, can't remember if they dispositioned the AAPL rec last night. **Build**: a "Recent activity" collapsed timeline on Today bottom.
