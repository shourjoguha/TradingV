/**
 * Chart palette — SINGLE source of truth for chart hex literals.
 *
 * Replaces the drift-prone constants previously scattered across:
 *   - `components/macro/RatioChart.tsx`     PALETTE     (5 hexes)
 *   - `pages/PredictionsByTarget.tsx`        PREDICTION_COLORS (10 hexes + inline strings)
 *   - `lib/macro-views.ts`                   SECTOR_IDENTITY_HEX (9 hexes)
 *   - `components/macro/Sparkline.tsx`       inline (#5FAFA8, #E07A6F, #94A3B8)
 *   - `components/macro/CyclePhaseWheel.tsx` inline (#7A5AA8, #A0AEC0, ...)
 *   - `components/macro/CorrelationHeatmap.tsx` rgba(63 122 110), rgba(176 83 60)
 *
 * Hex values mirror `tailwind.config.js` `colors.identity.*` + `colors.success/danger/warning`.
 * If you change a value here, audit the Tailwind config too — the design tokens are
 * intentionally duplicated (Tailwind for CSS classes, this file for SVG/Plotly fill).
 *
 * Tagged with the 2026-05-17 color-recast.
 */

export const SURFACE = {
  /** Body bg color used by lightweight-charts + Plotly chart background (`#E0E5EC` neumorphic). */
  bg: '#E0E5EC',
  /** Default chart text color (matches `--foreground` HSL 213 28% 25%). */
  text: '#3D4852',
  /** Muted text — labels, ticks, secondary annotations. */
  textMuted: '#6B7280',
  /** Faint grid lines. */
  grid: 'rgba(61, 72, 82, 0.08)',
  /** Cell border on heatmaps / dot stroke on wheels. */
  hairline: '#A0AEC0',
} as const

/** Semantic — direction-of-state (up/down/neutral). Mirrors Tailwind `success/danger/warning`. */
export const SEMANTIC = {
  success: '#5FAFA8',
  danger: '#E07A6F',
  warning: '#D4A547',
  neutral: '#94A3B8',
} as const

/** Identity — content-type (Macro regime, narrative chrome, ambient). Mirrors Tailwind `identity.*`. */
export const IDENTITY = {
  inflation: '#C58A3D',
  growth:    '#3F7A6E',
  liquidity: '#4A6FA5',
  stress:    '#B0533C',
  narrative: '#7A5AA8',
  ambient:   '#5C7A8C',
} as const

/** Per-sector identity. SSGA SPDR sectors → identity hex. Hand-synced w/ `SECTOR_IDENTITY_BG`. */
export const SECTOR: Record<string, string> = {
  XLK: IDENTITY.liquidity,
  XLF: IDENTITY.narrative,
  XLE: IDENTITY.inflation,
  XLV: IDENTITY.growth,
  XLI: IDENTITY.stress,
  XLP: IDENTITY.ambient,
  XLY: IDENTITY.stress,
  XLU: IDENTITY.ambient,
  XLB: IDENTITY.inflation,
}

/**
 * Prediction-line palette — used by PredictionsByTarget to color N overlay lines.
 * Anchored on primary (graphite ink) + success/warning neighbors so the chart
 * stays inside the neumorphic system while still distinguishing N runs.
 *
 * 2026-05-17: pulled from PredictionsByTarget inline const. Names kept generic
 * (predictionA..J) so the palette can serve any "N-series-overlay" chart.
 */
export const PREDICTION_LINES = [
  IDENTITY.liquidity, // slate-blue
  IDENTITY.growth,    // forest-teal
  IDENTITY.narrative, // plum
  SEMANTIC.success,   // teal-green
  IDENTITY.inflation, // burnt ochre
  IDENTITY.stress,    // brick
  IDENTITY.ambient,   // steel
  '#7986CB',          // indigo neighbor (filler)
  SEMANTIC.warning,   // amber
  '#06B6D4',          // cyan neighbor (filler)
] as const

/** Candle up/down — mirrors SEMANTIC but named for explicit OHLC usage. */
export const CANDLE = {
  up: SEMANTIC.success,
  down: SEMANTIC.danger,
} as const

/**
 * Heatmap correlation gradient stops. Maps [-1, +1] → rgba w/ alpha.
 * Used by Plotly `colorscale` prop + the legacy bespoke heatmap fallback.
 */
export const CORRELATION_GRADIENT: Array<[number, string]> = [
  [0.0, 'rgba(176, 83, 60, 0.75)'],   // -1 → stress red
  [0.5, 'rgba(160, 174, 192, 0.10)'], //  0 → neutral grey
  [1.0, 'rgba(63, 122, 110, 0.75)'],  // +1 → growth green
]
