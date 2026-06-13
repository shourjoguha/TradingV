# UI components

`src/components/ui/*` — shadcn-style primitives, **handwritten** (not installed via `npx shadcn add`). All implement the **Neumorphism design system** — see "Theming" below.

## Currently shipped

`badge`, `button`, `calendar`, `card`, `date-picker`, `dialog`, `input`, `label`, `multi-select`, `popover`, `select`, `skeleton`, `sonner` (Toaster), `switch`, `table`, `textarea`, `toggle`, `toggle-group`. (Previously also `BackendToggle` — removed 2026-05-17 per [ADR 018](../decisions/018-railway-shutdown.md).)

### Floating surfaces — `popover`, `calendar`, `date-picker`, `multi-select`

- `popover.tsx` — Radix Popover wrapper. Content reads as an extruded card (`shadow-extruded`, `rounded-2xl`, `bg-card`) so floating UIs sit visually above the page surface (which is itself a same-color clay).
- `calendar.tsx` — `react-day-picker` v9 with neumorphic skin: violet extruded selected day, inset hover/focus on day buttons, inset chevron nav buttons. `optimizeDeps` and a single-React alias in [vite.config.ts](../../frontend/vite.config.ts) prevent the hoisted-React duplicate that triggers "Invalid hook call" with this lib.
- `date-picker.tsx` — composes `Popover` + `Calendar` + an Input-styled trigger button. Value/onChange take ISO `YYYY-MM-DD` strings (matches existing page state shape). UTC-stable: parses and emits via `Date.UTC` so anchor-mode date math doesn't drift across timezones.
- `multi-select.tsx` — searchable popover list with chip preview in the trigger (max 4 chips + "+N more" overflow), per-row checkmarks, "X selected" footer, Clear action. Trigger min-height grows with chip count; popover width matches trigger via `--radix-popover-trigger-width`.

## Pattern

Each is a Radix primitive + `cva` variants + `cn()` from `lib/utils.ts`.

```tsx
import * as Primitives from '@radix-ui/react-X'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'
```

## Theming — Neumorphism (Soft UI)

### Visual physics

Every interactive primitive maps to one of two states:
- **Extruded** — element raised off the page, dual shadows (light top-left, dark bottom-right). Used for resting state of buttons, cards, badges, and the icon-rail.
- **Inset** — element pressed into the page, shadows reversed inward. Used for inputs, tables (container), tab containers, sidebar nav active state, and pressed buttons.

Hover lifts buttons + cards 1px and deepens the shadow. Active presses 0.5px and flips to inset. Focus shows a 2px violet ring offset by 2px on the page background.

### Tokens (defined in `tailwind.config.js`)

| Token | Value | Where |
|---|---|---|
| `bg-background` / `bg-card` | `#E0E5EC` (cool clay) | All surfaces. Same as page. |
| `text-foreground` | `#3D4852` (dark blue-grey) | Primary text. WCAG AAA on background. |
| `text-muted-foreground` | `#6B7280` (cool grey) | Secondary text. WCAG AA. |
| `bg-violet` / `text-violet` | `#6C63FF` (accent) | CTAs, focus rings, active nav text. |
| `bg-success` / `bg-success-bg` / `text-success-fg` | teal `#5FAFA8` family | Up/buy/positive |
| `bg-danger` / `bg-danger-bg` / `text-danger-fg` | coral `#E07A6F` family | Down/sell/negative |
| `bg-warning` / `bg-warning-bg` / `text-warning-fg` | amber `#D4A547` family | Drift alerts, caution |
| `shadow-extruded` | `9px 9px 16px rgb(163,177,198,0.6), -9px -9px 16px rgba(255,255,255,0.5)` | Cards |
| `shadow-extruded-hover` | bigger spread | Hover state |
| `shadow-extruded-sm` | 5px spread | Small buttons, badges |
| `shadow-inset` / `shadow-inset-deep` / `shadow-inset-sm` | inset variants | Inputs, tables, wells |
| `rounded-2xl` (16px), `rounded-3xl` (24px), `rounded-4xl` (32px) | extended | Buttons / cards / large containers |

### Fonts

`Plus Jakarta Sans` (display, weights 500-800) + `DM Sans` (body, weights 400-700), loaded from Google Fonts in `src/index.css`. Use `font-display` class for headlines (mostly automatic via `CardTitle`, `DialogTitle`, page headings).

### CSS vars + dark mode

CSS vars in `src/index.css` `:root`. **Dark mode dropped** — no `.dark` block, no `darkMode: 'class'` in Tailwind config. Anti-pattern: don't add it back without an explicit dark-neumorphism design.

`* { border-color: transparent }` in `index.css` makes bare `border` utilities visually invisible — neumorphism uses shadows for edges, not borders. If you need a visible border (rare), set `border-color` explicitly.

### Anti-patterns (don't do)

- Don't use `bg-white` for cards. Cards must match the page (`bg-background`).
- Don't add hex shadows. Use `shadow-extruded*` / `shadow-inset*` tokens.
- Don't use `rounded-md` or sharper. Minimum is `rounded-xl` (12px); prefer `rounded-2xl` (16px) for buttons, `rounded-3xl` (24px) for cards.
- Don't add bare `border` utilities expecting them to render — they're transparent globally.
- Don't use the Tailwind default font weights for body text. Headlines = `font-display font-bold` or `font-extrabold`; body = no font class needed (DM Sans default).

## Type scale (2026-05-17 audit)

Operator complaint: surfaces felt "spacious yet crammed" — generous padding around small, dense text. Council recast type to a single canonical scale.

| Tier | Tailwind | Pixels / line-height | Use |
|---|---|---|---|
| display | `text-2xl` / `leading-tight` | 24 / 1.15 | Page H1, hero stat numbers |
| title   | `text-base` / `leading-snug`  | 16 / 1.30 | CardTitle (one canonical size), panel headers |
| body    | `text-sm` / `leading-normal`  | 14 / 1.55 | All readable copy: descriptions, list items, table cells |
| meta    | `text-xs` / `leading-snug`    | 12 / 1.40 | Timestamps, badges, secondary labels, table headers |

**Two hard rules**:
1. **No `text-[10px]`.** If it doesn't deserve 12px, it doesn't deserve to render — move to tooltip. (157 violations cleaned 2026-05-17.)
2. **No `uppercase tracking-wider` on labels under 14px.** Sacrifices ~30% legibility for "style." (88 violations cleaned 2026-05-17.)

**Spacing rhythm** (4-unit ladder): `space-y-{1, 2, 3, 4, 6}`. Don't use `1.5` or `5` — snap to neighbours. CardHeader/Content/Footer padding is `p-4 md:p-5`; only override to `p-6` on hero/single-card surfaces.

## Tooltip discipline

Use `<InfoBubble term="…">` (glossary) or `<InfoBubble content={…} label="…">` (ad-hoc) for any always-on copy that *explains* a thing rather than *shows new information*. Codified after the 2026-05-17 density audits removed CardDescriptions from Today's 4-up cards + Macro panel headers + Theses/Research/Macro/TheStreet page subtitles (~150px reclaimed across the Think section).

**`PageHeader` default**: `description` prop now renders as a hover (i)-icon, NOT an always-on subtitle. Pass `descriptionInline` only when the prose itself is operator-actionable.

The trim rule:
- If a sentence explains *why* a thing exists → tooltip
- If a sentence explains *what* the number is → tooltip
- If a sentence is a section's tagline that adds no new info ("Hypotheses tracking the regime + names") → tooltip
- Body copy is reserved for what the operator hasn't seen yet

## Color taxonomy (2026-05-17 council)

Operator wanted more color in a previously-grey UI; council (UX strategist + visual designer + motion designer) agreed: **color is a finite cognitive resource — spend it on data, not chrome**. Three families of tokens, each with its own rules.

### Family 0 — Primary (recast 2026-05-17)

`bg-primary` / `text-primary` / `border-primary` / `ring-primary` — **graphite ink `#2E3D52`**. Replaces the vibrant violet `#6C63FF` that the previous council picked (operator walked back from it). Use for active-focus signals only: active nav, CTA buttons, focus rings, K-logo, active tab text, primary links. Hover/active pair: `bg-primary-light` (#4A5C73, lighter), `bg-primary-active` (#1C2838, darker). **Never** use as a card background; reserve for ink-on-clay marks. The bare `violet` Tailwind alias has been removed — any reference is a regression.

### Family 1 — Semantic (existing)

`bg-success` / `bg-danger` / `bg-warning` + `-fg` / `-bg` variants. Encode **direction of state**: up / down / caution. Use for P&L sign, drift-tier thresholds (<.40 / <.70 / ≥.70), status badges (active / at-risk / invalidated, open / snoozed / acted / dismissed), rule-firing bands. **Don't repurpose** for anything not direction-of-state.

### Family 2 — Identity (new)

`bg-identity-{inflation,growth,liquidity,stress,narrative,ambient}` — each maps to a *kind of content*, orthogonal to direction-of-state.

| Token | Hex | Where |
|---|---|---|
| `identity-inflation` | `#C58A3D` (burnt ochre) | Macro/Inflation panel header bar |
| `identity-growth`    | `#3F7A6E` (forest-teal) | Macro/Growth panel header bar · also closed-trade *win* row 3px left-bar |
| `identity-liquidity` | `#4A6FA5` (slate-blue)  | Macro/Liquidity + Yield-curve panel header bars · rate-axis sparkline strokes |
| `identity-stress`    | `#B0533C` (brick)       | Macro/Stress panel header bar · also invalidated-thesis indicator + closed-trade *loss* row 3px left-bar |
| `identity-narrative` | `#7A5AA8` (plum)        | Theses cards (6px top-bar) · Research answer chrome (2px left rail) · TV-Context per-source dot |
| `identity-ambient`   | `#5C7A8C` (steel)       | Sparkline gridlines · Today's "What I'm curious about" card icon |

Use as 4px left-bars · dots · badge fills · sparkline strokes — **never as card backgrounds**. Card bodies stay clay.

### Family 3 — Motion (new — fires + decays)

`bg-wash-{success,snooze,dismiss}` — used only inside Tailwind `animate-disposition-wash-*` keyframes; not standalone backgrounds. K-logo ring uses `animate-attention-pulse` (defined in `tailwind.config.js` → `keyframes`). All washes/pulses have low chroma so they feel like light, not paint.

### The three rules (codified — break these, expect a review reject)

1. **Max 1 color-encoded dimension per row.** If two dimensions both deserve color (e.g. status AND time on Theses), use *one as edge-tint* and *one as fill-icon* — never two chips side by side.
2. **No new hex without a named identity entry.** Hex is implementation; tokens are intent. Add to this file + `tailwind.config.js` together.
3. **Color enters only when something committed / crossed / cleared.** Never on hover, never on focus, never as decoration. Hover stays a shadow lift; focus stays a violet ring; section nav stays grey-with-violet-active.

### Stays grey (do not paint)

Card bodies · page background · sidebar rail · table zebra · inputs · popovers · calendars · dialogs · skeletons · tab containers · sparkline plot areas · Research Q&A bodies · Admin · Docs · button hovers · focus rings · Predictions chart chrome.

## Compositions (canonical patterns) — read this BEFORE rolling a new chip / tab control

Multiple drift incidents have come from rolling a new chip/tab variant with raw `<button>` + Tailwind classes. Pick the right pattern from below.

### A. Page tabs — segmented neumorphic, route-driven

Used when the choice changes the URL path (e.g. `/predictions/horizon` ↔ `/predictions/target`). Route-driven so deep links work.

**Use the `TabbedShell` primitive** for new pages — `components/common/TabbedShell.tsx` (added 2026-05-17) wraps this pattern + ARIA + URL routing + lazy-mount in one component. Pass `tabs: [{id, label, render}]` + `basePath`. Detail short-circuit via `isDetail` + `detail` props.

Reference (using primitive): `Motion.tsx`, `ThesesShell.tsx`, `Predictions.tsx`.
Reference (hand-rolled, retained due to cross-tab shared state): `Macro.tsx` (has `since` filter), `Admin.tsx` (has `:jobId` detail param), `TheStreet.tsx`, `WatchlistConsolidated.tsx`.

```tsx
<div
  role="tablist"
  aria-label="<scope> view"
  className="inline-flex rounded-xl bg-background shadow-inset-sm p-1 gap-1"
>
  {TABS.map((t) => {
    const active = t.id === tab
    return (
      <button
        key={t.id}
        role="tab"
        aria-selected={active}
        onClick={() => navigate(...)}
        className={[
          'px-3 py-1.5 rounded-lg text-xs transition-all',
          active
            ? 'bg-card text-foreground shadow-extruded-sm font-medium'
            : 'text-muted-foreground hover:text-foreground',
        ].join(' ')}
      >
        {t.label}
      </button>
    )
  })}
</div>
```

Inset container (`shadow-inset-sm bg-background`), extruded active child (`bg-card shadow-extruded-sm`). Use `rounded-xl` outer + `rounded-lg` inner — NOT `rounded-2xl`.

### B. Filter chips — Badge variant, in-page state

Used when the choice filters in-page state (status filter, scope picker, skill picker). Local state, not URL.

Reference: `frontend/src/components/research/HistoryList.tsx`, `AskInput.tsx` (hypothesis scope), `SkillPicker.tsx`, `frontend/src/pages/Theses.tsx`.

```tsx
import { Badge } from '@/components/ui/badge'

<div className="flex items-center gap-2 flex-wrap">
  <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mr-1">
    {scopeLabel}
  </div>
  {FILTERS.map((f) => (
    <button
      key={f.id}
      type="button"
      onClick={() => setFilter(f.id)}
      className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet rounded-full"
    >
      <Badge
        variant={filter === f.id ? 'default' : 'outline'}
        className="cursor-pointer select-none"
      >
        {f.label}
      </Badge>
    </button>
  ))}
</div>
```

`Badge` ships the active treatment (`bg-violet text-white`) + outline treatment via `variant`. The outer `<button>` gives keyboard/focus semantics that `<Badge>` (a `<div>`) lacks.

### C. Decision matrix

| Question | Answer |
|---|---|
| Does the choice change the URL? | Pattern A |
| Does it filter in-page state without changing the route? | Pattern B |
| Multiple choices selectable? | `multi-select.tsx` primitive (popover w/ chip preview) |
| Single binary on/off? | `switch.tsx` primitive |
| Long-form copy + icon row of multiple actions? | not a chip — use a `Card` with full-width buttons |

### D. Anti-pattern (don't do)

- ❌ `rounded-full border px-3 py-1 text-xs ... bg-violet text-white border-violet` — that's a hand-rolled clone of `<Badge variant=default>`. Use the primitive.
- ❌ `rounded-2xl ... text-violet bg-background shadow-extruded-sm` for in-page filters — that's pattern A leaking into pattern B's territory. Use Badge for filters.
- ❌ Mixing variants on the same page (Macro uses A, Theses uses B — that's fine because they serve different purposes; but don't ship both A and B for the same kind of control on the same page).

## Adding a new primitive

1. **shadcn CLI**: `npx shadcn@latest add <name>` then **rewrite** with neumorphic shadows + radii. The CLI default ships flat shadcn, not our look — it WILL look out of place if you skip the rewrite.
2. **Hand-write**: copy the existing primitive that's closest in interaction model and adapt. Rule: every interactive element gets `shadow-extruded-sm` or larger at rest, hover lifts + deepens, active = inset-sm.

## `cn()`

`clsx` + `tailwind-merge`. Use whenever combining classes, especially conditional. Lives in `lib/utils.ts`.

## `components/common/*` primitives (above `ui/*` shadcn primitives)

Composition-layer primitives that solve cross-page concerns. Use these instead of hand-rolling.

| Primitive | File | Use when |
|---|---|---|
| `DriftBar` | `common/DriftBar.tsx` | Rendering a 0..1 scalar (drift score) as a colored bar + tabular-nums label. Sizes `sm / md / lg`. Aria meter built-in. |
| `StatusBadge` | `common/StatusBadge.tsx` | Status pill across rec / hypothesis / trade / opportunity / position / flag. Use `kind` + `value`; never hand-roll the color combo. |
| `TabbedShell` | `common/TabbedShell.tsx` | Page-tab segmented control (Pattern A above) + URL routing + ARIA. See Pattern A for migration list. |
| `PageHeader` | `common/PageHeader.tsx` | Page H1 w/ violet anchor bar + icon slot + actions slot. Default mode (3xl extrabold) vs `tight` mode (2xl). |
| `PageWithSidecar` + `SidecarTile` | `common/DetailSidecar.tsx` | Two-column page shell (main + right rail at xl breakpoint, stacked below). Use to populate former empty grey clay below list pages. |
| `LazyRoute` | `common/LazyRoute.tsx` | Wraps `lazy()`-ed page in Suspense + Skeleton fallback. Replaces inline `<Suspense fallback={<Skeleton …/>}>...</Suspense>` per-route. |
| `RecCard` (rx-specific) | `components/rx/RecRow.tsx` | Mobile-stacked rec card variant; rendered at `<md` viewports paired with the desktop table at `≥md`. |
| `useUrlState` | `hooks/use-url-state.ts` | Sync filter/sort state to URL so back-button + deep-link work. Opt-in per page. |

Added 2026-05-17 in the UX rework — decisions log at `.claude/decisions/ux-rework-2026-05-17/`.

## Charts

Three-tier chart infra (SVG primitives / Plotly Tier-2 / ChartBuilder Tier-3) lives at `components/charts/`. Full reference — decision table, theme contract, ChartBuilder usage, plotly-bundle policy, migration history — moved to its own page: **[charts.md](charts.md)**.

Quick rules:
- Tier 1 SVG for cell-density use (`Sparkline`, `DriftBar`, `MiniCandleCompare`)
- Tier 2 Plotly for expanded views (`LineChart`, `CandlestickChart`, `Heatmap`, `PolarRadial`, `BumpChart`) — lazy-load the consuming page
- Tier 3 `ChartBuilder` for operator-composable multi-pane charts w/ URL state
- All colors from `components/charts/theme/palette.ts` — never hardcode hex in chart code

## Don't

- Don't import from `lucide-react` deep paths. Use top-level: `import { Foo } from 'lucide-react'`.
- Don't write inline `<style>` — Tailwind only.
- Don't add a new primitive without a use case in a page. Code dies in `ui/` fastest.
- Don't hand-roll a page tab strip — use `TabbedShell`.
- Don't hand-roll a status pill — use `StatusBadge`.
- Don't hardcode chart colors. Pull from `components/charts/theme/palette.ts`.
- Don't use Tier 2 (Plotly) in dense lists / table cells. Per-cell Plotly balloons DOM + memory; use a Tier 1 SVG primitive instead.
