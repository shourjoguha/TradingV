# Visual Designer — Council Review (2026-05-17)

Scope: visual hierarchy, density, color semantics, typography, card vocabulary, status systems, mobile.
Out of scope: information architecture and vault/ingest tooling.

Evidence pulled from `.audit/v2-01..v2-07` and `01..09` PNGs, and the live source under `frontend/src/`.

---

## 1. The big picture (one paragraph before the issues)

The neumorphic system has been disciplined at the primitive layer (`badge.tsx`, `button.tsx`, `card.tsx`) but is being **bypassed at the page layer**. The audit shots show three independent badge dialects, two card vocabularies (extruded vs inset) used interchangeably, two number renderings (tabular vs proportional), and a vast amount of empty grey clay below tables that gives the app a "scaffolding" feel. The system is right; the application of it is drifting. The fix is mostly **constraint, not creativity** — kill the page-level ad-hoc styling and force every page through the design tokens.

---

## 2. Six P-ranked visual issues

### P0-1 — Three different status-badge dialects on screen at once
`RxFinance.tsx:20-31` uses raw tailwind colors (`bg-yellow-500/15 text-yellow-700 border-yellow-500/30`). `Theses.tsx:64-69` uses semantic tokens (`bg-success-bg text-success-fg`). `Trades.tsx:117` uses the canonical `<Badge variant="success">`. In `v2-02-recs.png` you can read three statuses (`open` yellow, `auto-revived` violet, `acted` green) that are visually unrelated to the `active` (green) status pill in `04-theses-health.png` and to the `BUY` pill in `v2-05-trades.png`. The operator's eye cannot triangulate "what does green mean here" across pages.
**Fix**: delete the `statusBadge()` helper in `RxFinance.tsx` and replace with the unified vocabulary in §4. All status renderings flow through one `<StatusBadge kind="rec|hypothesis|trade|opp|position" value="open">` component.

### P0-2 — Page-tab and section-tab live in the same visual register
`v2-02-recs.png` shows the page-tab strip ("Opportunities / Trades / Positions / Recommendations") rendered at almost identical scale and treatment to a chip group. Pattern A is meant to feel like a chassis-level control; here it looks like a filter chip cluster floating in the page. The page H1 ("Finance recommendations") sits at roughly the same visual weight as the tab strip — the tab strip wins the eye even though the H1 is the real "you are here."
**Fix**: shrink page tabs to `text-[11px]` uppercase + reduce horizontal padding; bump page H1 to `text-3xl font-extrabold` (currently `text-2xl font-bold` in most pages). Anchor the H1 with a 4px tall violet bar (`before:` pseudo) to claim hierarchy.

### P0-3 — Massive empty clay below tables (Theses Health, Positions, Trades, Recommendations)
`04-theses-health.png`, `v2-04-positions.png`, `v2-05-trades.png`, `v2-02-recs.png` all show a single inset table card followed by ~600px of nothing. Neumorphism without content reads as factory floor. This is the single largest aesthetic problem in the app.
**Fix**: every list/table page gets a right-rail sidecar (320–360px) with **rotating contextual context** — for `/recommendations`: the rec funnel histogram, recent dispositions, and "next rec drops in 14h"; for `/positions`: thesis-match score + concentration mini-bar chart; for `/trades`: a 30-day P&L sparkline + win-rate gauge. The table reflows to occupy `min(100%, 920px)` and the sidecar fills the void. This is the single highest-ROI visual change.

### P1-4 — Tabular numerals not enforced; column edges misalign
`v2-04-positions.png`: `$15,293` (header) reads in DM Sans proportional; `$182.50` (avg entry column) reads tabular; `+$685.00` (P&L) is tabular. `v2-02-recs.png`: `0.22`, `0.72`, `0.48`, `0.55` in DRIFT/CONF columns appear to be proportional — note how the decimal points fail to align. For a numbers-driven app this is the easiest credibility win to grab.
**Fix**: add a global `.num` utility (`font-variant-numeric: tabular-nums`) and apply to every `<td>` in tables plus every metric card value. Trivially shippable via a `Stat` and `NumCell` wrapper.

### P1-5 — Card vocabulary inversion: KPI cards are inset, list cards are extruded — should be reversed
`v2-04-positions.png` shows `PORTFOLIO VALUE / UNREALIZED P&L / OPEN POSITIONS` rendered as **inset** wells. The eye reads them as form fields rather than primary metrics. Meanwhile, the table containing the actual position data is also inset. Hierarchy collapses. Per `ui-components.md:30-34`, extruded = "raised off the page" (primary, attention-getting), inset = "pressed into the page" (input wells, secondary). Today's app inverts this on the most-viewed pages.
**Fix**: KPI/stat cards = `shadow-extruded` (they ARE the headline number). Tables = stay inset (they are dense reference surfaces). Action buttons = extruded. See §3 for the full vocabulary.

### P1-6 — Drift bars look like loading skeletons
`v2-02-recs.png` DRIFT column: short colored bars (green/red/amber). They have no axis, no scale label, no comparison frame. An operator who hasn't memorised the codebase will read them as "loading…" Coral red on cool clay #E0E5EC also dips below the WCAG AA 3:1 non-text contrast threshold at the rendered weight; not catastrophic but flag-worthy.
**Fix**: render drift as a small horizontal **diverging bar** centered on 0 (the threshold), with a 1px tick at threshold. Numeric value next to bar in tabular nums. Use `bg-danger` for above-threshold, `bg-warning` for borderline, `bg-success` for below. Min height 6px, min width 48px, max 80px.

### P2-7 — Modal contrast too low; "Save" button has insufficient lift
`v2-06-rec-to-trade.png` shows the Log Trade dialog hovering on a barely-darker grey overlay. The dialog itself is `bg-card` (same #E0E5EC as the page), so the only separation is the dialog's extruded shadow. On bright laptop screens this reads as a "ghost" panel. The violet Save button sits in the corner with no contrast against the inputs around it.
**Fix**: bump dialog backdrop to `bg-foreground/15` (currently appears to be ~6%). Pull Save to bottom-right with explicit `shadow-extruded-hover` rest state — make it the most-extruded element in the modal so the eye lands on it last.

### P2-8 — Empty states are dead grey, not teaching surfaces
`v2-01-today.png`: "Recent TV Context — no recent context found" reads as a forgotten panel. `04-theses-health.png` "RECENT RECS" all `—`. The operator gets no "next action" cue.
**Fix**: every empty state shows (1) one-line "why this is empty," (2) one **primary button** for the next action, (3) optional icon. Reference compact: `<EmptyState icon={Inbox} title="No TV context yet" hint="Paste a chart or alert on /tv-context" action={<Button to="/tv-context">Open inbox</Button>} />`.

### P2-9 — Sidebar status footers ("OPEN RECS / HYPOTHESES") are the brightest objects on the page
`v2-04-positions.png` left rail: the two pinned cards have extruded shadow + larger contrast than the actual position numbers in the main pane. Sidebar is supposed to be ambient, not loud.
**Fix**: drop these to `shadow-inset-sm` with `text-muted-foreground` for labels. Numbers in `text-foreground` tabular only.

### P2-10 — Mobile responsive untested in audit
`Layout.tsx` mentions a mobile drawer but no `v2-*-mobile.png` exists. Tables in current form will horizontal-scroll into oblivion. Recommendations table has 7 columns; trades has 9.
**Fix**: below `md:`, table-pages collapse to a stacked card list (`<TradeCard />`, `<RecCard />`). Already half-built in the rec-detail page — extract the card body and reuse.

---

## 3. Card vocabulary proposal

Resolves the inversion in P1-5 by binding a card's physics (extruded vs inset) to its **semantic role**, not the author's mood.

| Role | Physics | Radius | Shadow | Example |
|---|---|---|---|---|
| Hero stat / headline metric | extruded | `rounded-3xl` | `shadow-extruded` | Portfolio value, total P&L |
| Action card (primary CTA inside) | extruded | `rounded-3xl` | `shadow-extruded` | "Run Now" tile, "Log trade" |
| List / table container (reference data) | inset | `rounded-2xl` | `shadow-inset-sm` | Recs table, trades table |
| Inline mini-tile (Today strip items) | inset | `rounded-2xl` | `shadow-inset-sm` | Fresh signals strip |
| Sidebar ambient pin | inset | `rounded-2xl` | `shadow-inset-sm` | "OPEN RECS" footer |
| Floating dialog / popover | extruded | `rounded-3xl` | `shadow-extruded-hover` | Log trade modal |
| Page-tab segmented control | inset shell, extruded thumb | `rounded-xl` outer, `rounded-lg` inner | per `ui-components.md:82-106` | All page tabs |
| Status / signal pill | inset | `rounded-full` | `shadow-inset-sm` | All Badges |

Sizing rules: outer page-wrap cards use `rounded-3xl`, table containers `rounded-2xl`, pills `rounded-full`. Never use `rounded-xl` on a top-level card (reserved for nested controls). Never use anything smaller than `rounded-lg`.

---

## 4. Unified status badge system

Replaces three drifted dialects with one `<StatusBadge>` component (proposed at `frontend/src/components/ui/status-badge.tsx`).

| Conceptual state | Semantic token | Badge variant | Examples |
|---|---|---|---|
| **Live / in-progress** (action expected) | warning | `warning` | rec.open, opportunity.fresh |
| **Active / on-track** (no action needed) | success | `success` | hypothesis.active, trade.open (when in-profit), position.healthy |
| **Resolved positive** (operator acted, good) | success solid | `default` (violet) → revise to `success-solid` | rec.acted, trade.closed-win |
| **Resolved neutral** (operator chose to skip) | muted | `secondary` | rec.dismissed, hypothesis.cancelled |
| **Resolved negative** (broke or invalidated) | danger | `destructive` | hypothesis.invalidated, trade.closed-loss, opportunity.expired |
| **System-touched** (auto-revived, auto-promoted) | violet outline | new `system` variant | rec.auto_revived, hypothesis.auto_promoted |
| **Snoozed / deferred** | secondary outline | new `deferred` variant | rec.snoozed |
| **Flag — aging** | warning outline | `warning` + outline | rec aging ≥14d |
| **Flag — forced** | danger outline | `destructive` + outline | rec snooze_count≥2 |

API:
```tsx
<StatusBadge kind="rec" value="open" flags={['aging', 14]} />
<StatusBadge kind="hypothesis" value="active" />
<StatusBadge kind="trade" value="closed" pnl={+12.4} />
```
The component internally maps `(kind, value)` → variant. Pages stop choosing colors. Refactor target files: `RxFinance.tsx:20-31`, `Theses.tsx:64-69`, `Trades.tsx:117`, `Opportunities.tsx`, `RxFinancePositions.tsx`.

---

## 5. Three "reimagine" sketches (not polish — structural)

### A. Today page — replace 4-tile grid with a single "narrative strip"
Current (`v2-01-today.png`): four 2×2 tiles ("Where's it nailing / Where it might pounce / What it's curious about / Market mood") wrapped in extruded cards, each with ~3 lines of body. Information density is low; the four-up grid feels like a marketing page, not a trading dashboard.
**Reimagine**: single horizontal "morning briefing" card with four inline sections separated by 1px violet dividers, each ~25% width on desktop, stacked on mobile. Each section is one stat + one sentence. Above this strip: a **single hero metric** ("4 fresh signals · 2 forced recs · 0 stops triggered overnight") in `text-4xl font-extrabold tabular-nums`. Below: existing Open recommendations table, but as the **primary surface**, not buried 600px down the page.

### B. Recommendations page — kill the table, ship a "decision queue"
Current (`v2-02-recs.png`): standard 7-column table. The operator needs to read every column to decide.
**Reimagine**: queue of vertically-stacked rec cards (~96px tall each), one per row. Left edge: 4px colored bar (warning/success/danger via status). Left column: ticker in `text-2xl font-extrabold` + status badge. Middle: TLDR in `text-base`. Right: drift sparkline + confidence ring + "Disposition" inline buttons (act / snooze / dismiss). Operator can keyboard-navigate j/k and act with a/s/d. This matches how the operator actually uses the page (sequential decision, not lateral comparison).

### C. Trades page — merge KPIs into a single chart-card
Current (`v2-05-trades.png`): three big inset KPI cards ($0.00 P&L / 0 closed / 2 open) with massive whitespace, table below.
**Reimagine**: one wide hero card (`shadow-extruded`, `rounded-3xl`) that contains a small equity curve sparkline + the three numbers inline as captions to the chart, plus a 30-day win-rate gauge. Reclaim the vertical real estate above the table. Table itself loses the "ACTION" column — click the row to open detail (closing happens in the drawer). This is one of the few pages where a chart is functionally necessary.

---

## 6. Drift inventory (cite-and-shame)

| File:line | Drift | Canonical |
|---|---|---|
| `RxFinance.tsx:28-31` | Raw `bg-yellow-500/15 text-yellow-700` | `<StatusBadge kind="rec" value="open" />` |
| `RxFinance.tsx:105-111` | Raw `text-red-600 border-red-500/40` for flags | `<StatusBadge ... flags={['aging']} />` |
| `Theses.tsx:64-68` | `Badge variant="outline" className="bg-success-bg text-success-fg"` — variant+className collision | Add `success-outline` variant to badge primitive |
| `Trades.tsx:117` | `<Badge variant={t.side==='buy'?'success':'destructive'}>` — semantic miscoding (side is not P&L) | New `side` variant: neutral teal/coral with `BUY/SELL` text token, separate from win/loss |
| `Today.tsx` strip components mix `rounded-2xl` extruded + inset on neighboring tiles | Pick one per row | See §3 vocabulary |
| All metric cards in `v2-04-positions.png` | Inset wells used for primary numbers | Flip to `shadow-extruded` per §3 |
| All page H1s (`Theses.tsx`, `Positions`, `Trades`, `RxFinance`) | `text-2xl font-bold` | `text-3xl font-extrabold font-display` with 4px violet anchor bar |
| Table column headers across all list pages | Mixed `uppercase tracking-wider text-xs` and plain `text-sm` | Single `<Th>` primitive: `text-[10px] font-mono uppercase tracking-[0.08em] text-muted-foreground` |

---

## 7. Hierarchy + typography cheat sheet (target spec)

| Element | Class |
|---|---|
| Page H1 | `text-3xl font-extrabold font-display tracking-tight` + 4px violet `before:` bar |
| Section H2 | `text-lg font-bold font-display` |
| Card title | `text-sm font-semibold uppercase tracking-wider text-muted-foreground` |
| Hero metric | `text-4xl font-extrabold tabular-nums tracking-tight` |
| Table headers | `text-[10px] font-mono uppercase tracking-[0.08em] text-muted-foreground` |
| Table cells (numeric) | `tabular-nums text-sm` |
| Table cells (text) | `text-sm` |
| Badges | (delegated to StatusBadge — never hand-style) |
| Helper / hint text | `text-xs text-muted-foreground` |

---

## 8. What to ship first (if I only get one PR)

The `StatusBadge` primitive + refactor of the three drifted files (`RxFinance.tsx`, `Theses.tsx`, `Trades.tsx`). It's the smallest diff with the largest perceived-quality jump, because status pills are the most-repeated visual element in the app and the drift is the most jarring. Second PR: KPI card flip from inset → extruded everywhere (P1-5). Third PR: right-rail sidecars to kill empty clay (P0-3). Everything else is iteration.
