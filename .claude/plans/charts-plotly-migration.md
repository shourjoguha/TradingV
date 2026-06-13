# Chart infra refactor + Plotly migration

**Status:** ✅ **COMPLETE** (Phases 0-6 shipped 2026-05-17). Retro in `.claude/status/roadmap-shipped.md`.

**Created:** 2026-05-17
**Origin:** operator request after reading `.claude/plans/chart-modularity-handover.md`. Wants both (a) chart-infra reorg/centralization and (b) move to Plotly for complex viz patterns lightweight-charts can't serve.

## Operator's locked decisions

| Q | Choice |
|---|---|
| Plotly bundle | **Custom build** via `plotly.js/lib/core` + `Plotly.register([Scatter, Heatmap, Bar, Candlestick, ScatterPolar])` (~700KB target) |
| Two-tier rendering | **SVG primitives for cheap/embedded use** (sparklines, popovers, card widgets); **Plotly for expanded/detailed views** (Macro ratio drill-in, future complex viz). Operator points us at the tier per surface. |
| Migration scope | Staged: theme lib + RatioChart first, rest later |
| Sparkline/DriftBar/MiniCandle | Keep as inline SVG (fix the divide-by-zero bug separately) |
| Visual regression | Playwright screenshots of all chart surfaces before each migration |

## Audit corrections vs `chart-modularity-handover.md`

The handover doc was directionally right but missed/under-counted:

1. **PredictionsByHorizon.tsx (526 LOC) embeds `MiniCandleCompare`** — inline SVG candle viz, audit missed because it uses Tailwind class strokes instead of hex literals. Add to inventory.
2. **PredictionsByTarget.tsx is 516 LOC** (audit said 350). Win #1 effort estimate (~1h) is too low; realistic 2-3h.
3. **Sparkline divide-by-zero confirmed** (Sparkline.tsx:74). Z-scored series whose `values[0] == 0` → NaN/Infinity in delta. Fragile under Sectors ladder z-score input.
4. **0 frontend test files**. Refactor risk is real; Playwright baselines mandatory.
5. **36 hex literals across chart files** (handover top-5 added up to ~53 but inflated some files).

## Target architecture — two-tier charts

```
components/charts/
  svg/                # Tier 1: cheap, inline, embedded — no plotly
    Sparkline.tsx        # MOVED from components/macro/; fix divide-by-zero
    DriftBar.tsx         # MOVED from components/common/
    MiniCandleCompare.tsx # EXTRACTED from PredictionsByHorizon
  plotly/             # Tier 2: feature-rich, expanded views — lazy-loaded
    PlotlyChart.tsx      # base wrapper: theme + ResizeObserver + loading/empty/error
    LineChart.tsx        # REPLACES RatioChart (expanded macro ratio drill-in)
    CandlestickChart.tsx # REPLACES PredictionsByTarget inline createChart
    Heatmap.tsx          # REPLACES CorrelationHeatmap render path (Plotly Heatmap)
    PolarRadial.tsx      # REPLACES CyclePhaseWheel SVG (scatterpolar w/ tail support)
  theme/
    palette.ts           # SINGLE source of truth: semantic + identity + prediction colors
    layout.ts            # Plotly layout template tied to neumorphic CSS vars
    tokens.ts            # heights/fonts/strokes
  plotly-bundle.ts    # custom build: import core + register subset; lazy entry
```

Domain wrappers in `components/macro/*` collapse to ~30 LOC each (fetch data → pass to charts/plotly primitive). `RegimeConditionalBadges.tsx` (not a chart) and `RotationFootprintStrip.tsx` (CSS grid; arguably not chart material — re-evaluate after Phase 2) stay put.

## Phases

### Phase 0 — baselines (~30 min)
- Add Playwright dep + minimal config (no install of full @playwright/test if too heavy — use `npx playwright screenshot`).
- Capture before-screenshots: `/macro`, `/macro/ratios`, `/macro/sectors` (all 4 dropdown viz), `/predictions/target`, `/predictions/horizon`, `/today`. Save under `frontend/.audit/baselines/<route>.png`.

### Phase 1 — theme lib + Plotly base (~2h)
- Create `components/charts/theme/palette.ts` — pull from `tailwind.config.js`, export semantic/identity/prediction palettes as named consts. Backfill `SECTOR_IDENTITY_HEX` from this.
- Create `components/charts/theme/layout.ts` — Plotly `layout.template` w/ neumorphic bg (`#E0E5EC`), JetBrains Mono font, hidden default modebar buttons, custom hover style.
- Create `components/charts/plotly-bundle.ts` — `Plotly.register([Scatter, Heatmap, Bar, Candlestick, ScatterPolar])` against `plotly.js/lib/core`. Default export the lean `Plotly` instance.
- Create `components/charts/plotly/PlotlyChart.tsx` — wrapper around `react-plotly.js/factory` w/ lazy bundle import, ResizeObserver, loading/empty/error states. Memo on prop reference.
- `npm i plotly.js react-plotly.js @types/react-plotly.js` (operator approval implicit by saying "custom build").
- Verify bundle delta locally (`npm run build` → size check).

### Phase 2 — RatioChart → Plotly LineChart (~1.5h)
- Build `components/charts/plotly/LineChart.tsx` consuming `MacroPoint[]` + optional overlay.
- Swap `components/macro/RatioChart.tsx` to re-export `<LineChart>` (keeps callers stable: `Macro.tsx`, `SectorStrip.tsx`, `DetailSidecar.tsx`).
- Delete the inline `PALETTE` const.
- Playwright diff `/macro/ratios` + `/macro/sectors`. Reject if visual delta > minor.
- Append retro entry.

### Phase 3 — PredictionsByTarget → Plotly CandlestickChart (~3h)
- Build `components/charts/plotly/CandlestickChart.tsx`: ohlc bars + N overlay lines.
- Swap PredictionsByTarget's `useEffect`-driven `createChart` block (~150 LOC) for a 10-LOC `<CandlestickChart>` call.
- Move `PREDICTION_COLORS` to `theme/palette.ts`.
- Playwright diff `/predictions/target`. Cross-fingers for the 2-point line edge case (lines 164-189).
- Append retro.

### Phase 4 — drop lightweight-charts (~15 min)
- `npm uninstall lightweight-charts`.
- Bundle re-measure; confirm net delta vs Phase 1 baseline.
- Update CLAUDE.md / docs that reference lightweight-charts.

### Phase 5 — bespoke SVG → Plotly (optional, operator-gated) (~4h)
- CorrelationHeatmap → `<Heatmap>` (free zoom/hover/colorbar from Plotly).
- CyclePhaseWheel → `<PolarRadial>` (scatterpolar; gains true tail trail support for future RRG-style viz).
- RotationFootprintStrip → re-evaluate: may be fine as CSS grid (Plotly heatmap is heavier; only worth it if a 2nd viz needs the primitive).
- Per-phase Playwright diff.

### Phase 6 — folder reorg + Sparkline fixes (~2h)
- Move `Sparkline.tsx`, `DriftBar.tsx` into `components/charts/svg/`.
- Extract `MiniCandleCompare` from PredictionsByHorizon into `components/charts/svg/`.
- Fix Sparkline divide-by-zero (guard `values[0] === 0` → use absolute delta or skip pct display).
- Update all imports (5 callsites for Sparkline, 3 for DriftBar, 1 for MiniCandle).
- Update `.claude/frontend/ui-components.md` w/ two-tier charts section.

## Files affected (running list)

**New**:
- `frontend/src/components/charts/theme/palette.ts`
- `frontend/src/components/charts/theme/layout.ts`
- `frontend/src/components/charts/theme/tokens.ts`
- `frontend/src/components/charts/plotly-bundle.ts`
- `frontend/src/components/charts/plotly/PlotlyChart.tsx`
- `frontend/src/components/charts/plotly/LineChart.tsx`
- `frontend/src/components/charts/plotly/CandlestickChart.tsx`
- `frontend/src/components/charts/plotly/Heatmap.tsx` (Phase 5)
- `frontend/src/components/charts/plotly/PolarRadial.tsx` (Phase 5)
- `frontend/.audit/baselines/*.png` (Playwright)

**Moved**:
- `components/macro/Sparkline.tsx` → `components/charts/svg/Sparkline.tsx`
- `components/common/DriftBar.tsx` → `components/charts/svg/DriftBar.tsx`
- `MiniCandleCompare` (inline in PredictionsByHorizon.tsx) → `components/charts/svg/MiniCandleCompare.tsx`

**Modified**:
- `components/macro/RatioChart.tsx` (re-export, then delete in P4)
- `components/macro/CorrelationHeatmap.tsx` (Phase 5)
- `components/macro/CyclePhaseWheel.tsx` (Phase 5)
- `components/macro/RegimePanel.tsx`, `SectorLadderCard.tsx`, `SectorStrip.tsx`, etc. (import path updates)
- `pages/PredictionsByTarget.tsx` (Phase 3)
- `pages/PredictionsByHorizon.tsx` (Phase 6 — extract MiniCandle)
- `frontend/package.json` (add plotly, drop lightweight-charts)
- `frontend/src/lib/macro-views.ts` (drop SECTOR_IDENTITY_HEX → import from palette)
- `.claude/modules/macro.md`, `.claude/frontend/ui-components.md`, `.claude/status/roadmap-shipped.md`

## Open risks

1. **Bundle target ~700KB may slip** — custom build adds modules per chart type. Each register call adds ~80-150KB. Worst case 1.2MB.
2. **Plotly theming friction** — neumorphic look depends on bg color + custom font + suppressed modebar. Layout template may need iteration to match.
3. **react-plotly.js re-render perf** — naive prop changes redraw whole chart. Mitigate w/ `React.memo` + stable prop refs.
4. **Sparkline divide-by-zero fix may change visible delta values** on z-scored series — acceptable; current behavior is buggy.
5. **Playwright headless rendering may not match dev-server** for neumorphic shadows (px-perfect shadow rendering depends on subpixel AA). Use tolerance threshold in diff.

## Stop-and-decide gates

- After Phase 1: confirm bundle size acceptable. If >1MB after gzip, switch to `plotly.js-cartesian-dist` or stop.
- After Phase 2: confirm RatioChart visual parity. If neumorphic feel lost, escalate to operator before continuing.
- After Phase 4: re-decide whether Phase 5 (bespoke SVG migration) is worth it. CyclePhaseWheel may be better left as bespoke SVG.
