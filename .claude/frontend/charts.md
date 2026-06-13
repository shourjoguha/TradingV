# Charts — three-tier infra

> Single reference for all chart concerns. Everything chart-related routes through here. Migration history + per-phase retros live in `.claude/plans/charts-*.md` + `.claude/status/roadmap-shipped.md` (top 4 entries).

## Where the files live

```
frontend/src/components/charts/
  svg/                  # Tier 1 — zero-cost inline SVG primitives
    Sparkline.tsx          (5 callsites: Today, SectorStrip, DetailSidecar,
                            RegimePanel, SectorLadderCard)
    DriftBar.tsx           (3 callsites: RxStrip, RecRow, RxFinance)
    MiniCandleCompare.tsx  (1 callsite: PredictionsByHorizon)

  plotly/               # Tier 2 — Plotly-backed; lazy-loaded
    PlotlyChart.tsx        base wrapper (theme + ResizeObserver +
                           loading/empty states + onClick passthrough)
    LineChart.tsx          replaces lightweight-charts RatioChart
    CandlestickChart.tsx   replaces PredictionsByTarget inline createChart
    Heatmap.tsx            CorrelationHeatmap render (w/ onCellClick)
    PolarRadial.tsx        CyclePhaseWheel render (barpolar + scatterpolar)
    BumpChart.tsx          RotationFootprintStrip render

  builder/              # Tier 3 — composable multi-pane charts (URL state)
    ChartBuilder.tsx       N stacked panes + "Add pane"
    Pane.tsx               chart-type toggle + series chips + remove
    SeriesPicker.tsx       dropdown over AvailableSeries[] registry
    use-resolved-series.ts parallel useQueries (cache-aware)
    url-state.ts           compact text encode/decode for ?panes=…
    types.ts               SeriesSpec / PaneSpec / ChartType / AvailableSeries

  ChartTimeControl.tsx  # generic per-chart time-period toggle
                        # (preset-id → label). Used by rotation
                        # (cadence) + correlation (window).

  theme/                # single source of truth for chart colors
    palette.ts             SURFACE / SEMANTIC / IDENTITY / SECTOR /
                           PREDICTION_LINES / CANDLE / CORRELATION_GRADIENT
    layout.ts              Plotly BASE_LAYOUT + BASE_CONFIG
    tokens.ts              HEIGHT / FONT / STROKE presets

  plotly-bundle.ts      # custom Plotly build via plotly.js/lib/core
                        # registers: scatter, candlestick, heatmap,
                        # scatterpolar, barpolar
  index.ts              # full barrel
```

## Decision table — which tier?

| Tier | Use for | Bundle cost (gzip) |
|---|---|---|
| **1 — SVG** | Cells in a table, widgets in a card, popovers, anything embedded ≥3× per page | ~0 KB |
| **2 — Plotly** | Expanded views, drill-in modals, single-pane charts where pan/zoom/hover matter | +403 KB (lazy chunk, loaded only on `/macro` + `/predictions`) |
| **3 — Builder** | Operator-driven multi-pane composer w/ series picker + chart-type toggle + URL-persisted state | +5 KB on top of Tier 2 |

**Rules**:
- Never use Tier 2 in dense lists / table cells — per-cell Plotly balloons DOM + memory
- Never hardcode hex literals in chart components — import from `theme/palette.ts`
- Always lazy-load any page that imports from `components/charts/plotly/*` (App.tsx pattern) — keeps Plotly off the Today / Decide hot path
- New trace types: uncomment in `plotly-bundle.ts` + add to `Plotly.register([...])` — each register adds 30-150 KB

## Theme contract

All chart colors come from `components/charts/theme/palette.ts`. The constants mirror Tailwind tokens (`tailwind.config.js`) by intent — Tailwind tokens drive CSS classes, palette constants drive SVG fill + Plotly trace colors. If you change a hex in one, audit the other.

| Const | Source | Examples |
|---|---|---|
| `SURFACE` | bg, text, grid, hairline | `#E0E5EC`, `#3D4852`, `rgba(61,72,82,0.08)` |
| `SEMANTIC` | direction-of-state (up/down) | success / danger / warning / neutral |
| `IDENTITY` | content-type (Macro regime) | inflation / growth / liquidity / stress / narrative / ambient |
| `SECTOR` | per-SPDR-ETF identity | XLK→liquidity, XLE→inflation, etc. (9 sectors) |
| `PREDICTION_LINES` | N-series overlay palette | 10 colors anchored on IDENTITY |
| `CANDLE` | OHLC up/down | mirrors SEMANTIC.success/danger |
| `CORRELATION_GRADIENT` | heatmap colorscale stops | red(-1) → grey(0) → green(+1) |

## Tier 3 — ChartBuilder usage

Consume in a page component when the operator wants to pick series + stack panes:

```tsx
import {
  ChartBuilder,
  encodePanes,
  decodePanes,
  type PaneSpec,
  type AvailableSeries,
} from '../components/charts'

const available: AvailableSeries[] = ratioRows.map((r) => ({
  id: `${r.numerator}/${r.denominator}`,
  label: `${r.label} (${r.numerator} / ${r.denominator})`,
  build: () => ({
    kind: 'ratio',
    numerator: r.numerator,
    denominator: r.denominator,
    label: r.label,
  }),
}))

const [panes, setPanes] = useState<PaneSpec[]>(initialFromUrl)
// Sync `panes` ↔ `searchParams` via useEffect + useSearchParams.

return (
  <ChartBuilder
    panes={panes}
    onChange={setPanes}
    available={available}
    since={since}
  />
)
```

URL state format (`?panes=…`):

```
panes=ratio:XLK/SPY,ratio:XLE/SPY|type:line;ratio:HG/GC|type:area
```

- Semicolon `;` = pane separator
- Comma `,` = series-within-pane separator
- Pipe `|type:<line|area|log>` = chart type (default = line)
- Series fragment: `ratio:NUM/DEN[:LABEL]` or `series:SYM[:LABEL]`
- Bounded by query-string practical size ~2KB

**Cache-aware**: `useResolvedSeries` calls `useQueries` against the same TanStack cache keys (`macro-ratio`, `macro-series`) the rest of the app uses — adding a builder pane that shows a ratio another page already loaded is a free read.

**V1 scope**: ratio + series only. Spreads / OHLC / heatmap-as-pane deferred until a 2nd consumer surface demands them.

## Per-chart time controls

Page-level `1Y/3Y/5Y/10Y/Max` chips set the **data ceiling** (how far back to fetch). Per-chart time toggles select a window *within* that ceiling — operator can study recent rotation w/ a weekly bump while keeping the page set to 5y for the regime panels below.

| Chart | Preset axis | Presets | Maps to |
|---|---|---|---|
| Rotation footprint (`BumpChart`) | cadence + lookback | `12w` · `26w` · `1y · mo` · `3y · mo` · `5y · mo` | `weeklyRankMatrix(seriesBySymbol, periods, daysPerPeriod)` |
| Correlation matrix (`Heatmap`) | window (trading days) | `30d` · `90d` · `180d` · `1y` · `3y` · `5y` | `correlationMatrix(closesBySymbol, days)` + cascades to drill-in `rollingPairCorrelation(a, b, days)` |

Both surfaces clamp gracefully — picking a window longer than the page-level data window just uses what's available (`slice(-window-1)` for correlation, skip-snapshot for rotation). No errors.

Pattern: drop `<ChartTimeControl value onChange presets ariaLabel />` into the chart's CardHeader next to the `InfoBubble`. The control is preset-id generic so each chart defines its own `TimePreset<Id>[]` constant with whatever axis makes sense for it. Don't pass URL state — sectors page is exploration-mode; bookmark/share lives in the `/macro/ratios` ChartBuilder.

## Per-component playbook

| File | Use when | Don't use when |
|---|---|---|
| `Sparkline` | Inline cell line chart, ≤120px wide; needs trailing Δ% | You need pan/zoom or hover w/ exact x value |
| `DriftBar` | 0..1 scalar as colored bar + label; rec lists / strips | The value isn't bounded; non-drift semantics |
| `MiniCandleCompare` | Two side-by-side OHLC candles per cell (Actual vs Predicted) | You need axis lines, dates, or > 2 candles |
| `LineChart` | Single-series or overlay-pair time chart in a panel | You need OHLC bars |
| `CandlestickChart` | OHLC bars + optional N overlay lines (prediction overlays) | Pure-line is enough — use `LineChart` |
| `Heatmap` | 2D color-coded matrix w/ value labels + optional click drill-in | The "matrix" is really a 1D list — use `BumpChart` or `LineChart` |
| `PolarRadial` | Cyclical / RRG / quadrant viz w/ dots + quadrant tints | Series have no inherent angular meaning |
| `BumpChart` | Rank-over-time (conserved magnitudes) | Non-conserved flow magnitudes — pick a Sankey alternative if/when registered |
| `ChartBuilder` | Operator-composable multi-pane chart w/ URL state | Single chart w/ fixed config — use the underlying primitive directly |

## Plotly-bundle policy

Custom build via `plotly.js/lib/core` + selective `Plotly.register([...])`. Today's registered traces:

- `scatter` (Line / Bump / overlays)
- `candlestick` (PredictionsByTarget OHLC)
- `heatmap` (CorrelationHeatmap)
- `scatterpolar` (CyclePhaseWheel dots)
- `barpolar` (CyclePhaseWheel quadrants)

**To add a new trace**: import in `plotly-bundle.ts`, add to the `Plotly.register([...])` array. Each register adds 30-150 KB to the lazy chunk. Don't register speculatively — wait for a callsite.

## Lazy-loading + bundle constraints

- **Main bundle (hot path)**: 205 KB gzip — must stay clean of Plotly
- **PlotlyChart chunk (lazy)**: 403 KB gzip — loaded on `/macro` + `/predictions`
- **Macro chunk (lazy)**: 17 KB gzip — includes ChartBuilder + sectors viz wrappers
- **Predictions chunk (lazy)**: 36 KB gzip — includes PredictionsByTarget + Horizon

If you add a new chart-heavy page, lazy-load it in `App.tsx` (same pattern as Macro / Predictions). If you keep it eager-loaded, the Plotly bundle migrates back to main and the hot-path budget breaks.

## Migration + design history

| Doc | What's in it |
|---|---|
| `.claude/plans/chart-modularity-handover.md` | Pre-migration audit (chart-rendering surfaces, hex-literal density, reusable-vs-one-off classification, stress-test checklist). Historical reference — the audit hypothesis was largely correct. |
| `.claude/plans/charts-plotly-migration.md` | **Phases 0-6 plan** — Playwright baselines → theme lib + Plotly base → RatioChart migration → PredictionsByTarget migration → drop lightweight-charts → bespoke SVG migration → folder reorg + Sparkline divide-by-zero fix. Marked ✅ COMPLETE 2026-05-17. |
| `.claude/plans/charts-enrichment.md` | **Phases A-E plan** — BumpChart for rotation → click-drill on correlation → Tier 3 ChartBuilder primitive → Macro Ratios uses it → docs. Marked ✅ COMPLETE 2026-05-18. |
| `.claude/status/roadmap-shipped.md` | Per-phase retros (top 4 entries cover the chart arc). Read for the "why" behind decisions + skeptic-cleared declines. |

## Related routing

- Sectors viz (Cycle wheel / correlation / rotation / phase-confirm) wired through `pages/Macro.tsx` `SectorsTab` dropdown — see `.claude/modules/macro.md`
- Predictions chart (Candle + N overlay lines) wired through `pages/PredictionsByTarget.tsx` — see `.claude/modules/predictions.md` (if exists) or module README
- Today / Motion sparklines + drift bars wired through respective page components — pure Tier 1, no Plotly cost
