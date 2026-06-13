/**
 * Chart sizing + typography tokens. Used by Plotly layouts + SVG primitives
 * to keep proportions consistent across viz types.
 */

/** Chart height presets — matches the heights baked into existing chart callsites. */
export const HEIGHT = {
  /** Sparkline cell (32px) — inline in table rows / sector ladder cards. */
  spark: 32,
  /** Card-embedded chart (e.g. sector ladder drill-in). */
  card: 260,
  /** Default expanded chart (RatioChart default). */
  default: 320,
  /** Macro Ratios sub-tab expanded ratio view. */
  expanded: 420,
} as const

export const FONT = {
  /** Plotly font family — mono for axis ticks/numeric data. */
  mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
  /** Plotly font family — sans for labels/legend. */
  sans: '"DM Sans", system-ui, sans-serif',
  /** Axis tick + hover label size. */
  size: 11,
} as const

export const STROKE = {
  /** Primary chart line. */
  primary: 2,
  /** Overlay line (e.g. RatioChart overlay). */
  overlay: 1,
  /** Sparkline path. */
  spark: 1.4,
  /** Axis baseline. */
  axis: 1,
} as const
