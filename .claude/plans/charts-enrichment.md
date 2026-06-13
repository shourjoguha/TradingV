# Chart enrichment + ChartBuilder primitive

**Status:** ✅ **COMPLETE** (Phases A-E shipped 2026-05-18). Retro in `.claude/status/roadmap-shipped.md`.

**Created:** 2026-05-18
**Origin:** operator follow-up after Phases 0-6 of `charts-plotly-migration.md` shipped. Wants three enrichments + a generic chart-builder abstraction.

## Operator's locked decisions

| Q | Choice |
|---|---|
| Rotation footprint redesign | **Smoothed bump chart**, matte identity colors, sector labels on BOTH sides of Y-axis (left + right), no label repeated per bump |
| Correlation time-axis | **Click-cell drill-in** — cell click reveals rolling 90d Pearson of that pair as line below the matrix |
| ChartBuilder scope | **Extract generic primitive now** (`components/charts/builder/`) — Macro Ratios is first consumer, future services plug in |
| URL state | **Yes** — encode panes/ratios/type in query string so views are bookmark/share-able |

## Council deliberation summary

- **Visual designer**: bump chart > sankey for rank-over-time (Sankey is for non-conserved flow magnitudes; rank tracking is conserved)
- **Quant**: rolling corr / multi-ratio overlay / bump-chart series all derive from already-cached endpoints — zero new backend work
- **Skeptic**: operator override (wants abstraction now); keep the primitive minimal — JSON-driven config, no plugin system, no auto-save
- **Motion designer**: smoothed (`line.shape: spline`) bumps + 200ms transitions on data swap
- **UX strategist**: URL state bounded to ~2KB; serialize only deltas vs default

## Phased plan

### Phase A — Rotation bump chart (~2h)
- New `components/charts/plotly/BumpChart.tsx` — reusable rank-over-time scatter+lines, smoothed via `line.shape: 'spline'`, dual Y-axis labels (left + right), one trace per series w/ matte identity color.
- Take props: `{ series: Array<{ id, label, color, points: Array<{ t, rank }> }>, height?, yLabelLeft?, yLabelRight? }`.
- Replace render path in `components/macro/RotationFootprintStrip.tsx` — domain wrapper now shapes weekly footprint data into bump series. Rename to `RotationBump.tsx`? Decision: keep filename for caller stability, but rewrite contents.
- Y-axis: integer ranks 1..9, inverted (1 at top), tick labels = sector symbols on both sides via Plotly `mirror: 'allticks'` w/ overlay shape annotations.
- Hover: "XLK · Week of 2026-04-12 · Rank 1".

### Phase B — Correlation click-drill (~1.5h)
- Extend `components/charts/plotly/Heatmap.tsx` w/ optional `onCellClick(row, col, value)` prop.
- `CorrelationHeatmap.tsx` consumes click → stores selected pair → renders new `<LineChart>` below w/ rolling 90d Pearson series.
- New helper `rollingPairCorrelation(seriesA, seriesB, window=90)` in `lib/sector-strength.ts` — for each day `t`, compute Pearson on the trailing 90-day log-return window. Pure function.
- Clear-selection button + visual highlight on selected cell (Plotly shape overlay).

### Phase C — ChartBuilder primitive (~4h)
- New `components/charts/builder/` directory:
  - `ChartBuilder.tsx` — main composer. Props: `defaultPanes`, `availableSeries`, `onChange?`. Renders array of `<Pane>` components + "Add pane" button. URL-state hooked via `useUrlState`.
  - `Pane.tsx` — single pane: series picker(s) + chart-type toggle + remove-pane button. Internal `<LineChart>` or chart per `chartType`.
  - `SeriesPicker.tsx` — typeahead/dropdown over `availableSeries` (registry-driven). Resolves series via the right TanStack hook.
  - `types.ts` — `PaneSpec`, `SeriesSpec`, `ChartType`, `AvailableSeries`.
  - `url-state.ts` — encode/decode pane config to/from query string. Compact base64-JSON or named keys (`?panes=ratio:XLK/SPY,XLE/SPY|type:line|window:5y;ratio:HG/GC|type:area|window:5y`).
- Constraint: NO data fetching inside builder; builder hands off `SeriesSpec` to chart components which use existing hooks. Cache-aware out of the box.

### Phase D — Macro Ratios uses ChartBuilder (~2h)
- Rewrite `RatiosTab` in `pages/Macro.tsx` to be `<ChartBuilder defaultPanes={[{ series: [defaultRatio], chartType: 'line' }]} availableSeries={ratioRegistry} />`.
- `ratioRegistry` derived from existing `ALL_ROWS` constant; same labels.
- Single default pane = same chart as today; URL gives "+ pane" / "+ ratio" / chart-type controls.
- Preserve existing default UX so non-power-user flow is identical.

### Phase E — Docs + retro
- Update `.claude/frontend/ui-components.md` Charts section w/ ChartBuilder usage example.
- Update `.claude/modules/macro.md` w/ new Ratios builder + bump-chart redesign.
- Append retro entry in `.claude/status/roadmap-shipped.md`.

## Files affected

**New**:
- `frontend/src/components/charts/plotly/BumpChart.tsx`
- `frontend/src/components/charts/builder/{ChartBuilder.tsx,Pane.tsx,SeriesPicker.tsx,types.ts,url-state.ts}`
- `frontend/src/lib/sector-strength.ts` — `rollingPairCorrelation` helper added

**Modified**:
- `frontend/src/components/macro/RotationFootprintStrip.tsx` — domain wrapper using BumpChart
- `frontend/src/components/macro/CorrelationHeatmap.tsx` — click-drill state + LineChart below
- `frontend/src/components/charts/plotly/Heatmap.tsx` — `onCellClick` prop
- `frontend/src/pages/Macro.tsx` — RatiosTab becomes ChartBuilder consumer
- `frontend/src/components/charts/index.ts` — barrel exports for new entries

## Open risks

1. **URL state bloat** — many panes + many series + long since-window encodings could push past ~2KB. Mitigation: encode only deltas vs default; truncate to N panes/series w/ a friendly error.
2. **Bump chart label collision** — 9 sectors on Y-axis at integer ticks; if two sectors share rank on the same week, labels stack. Mitigation: Plotly's text-position offset + opacity for ties.
3. **Heatmap click events** — Plotly `onClick` fires for legend clicks too; need to filter to data points only.
4. **Bundle creep** — no new trace registrations needed (scatter, heatmap, scatterpolar already in `plotly-bundle.ts`). Bundle delta = ChartBuilder code ~5-8 KB gzip on the lazy Plotly chunk.
5. **ChartBuilder over-genericization** — keep config narrow: ratio + series only for V1, no spreads / OHLC / heatmap-as-pane until a 2nd surface needs them.
