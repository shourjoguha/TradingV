/**
 * Two-tier chart infra barrel.
 *
 * Tier 1 (cheap, inline): SVG primitives in `./svg/` — Sparkline, DriftBar,
 * MiniCandleCompare. Use these for table cells, card widgets, popovers,
 * anything embedded in a list (>3 instances per page). Zero plotly cost.
 *
 * Tier 2 (rich, expanded): Plotly-backed in `./plotly/` — LineChart,
 * CandlestickChart, Heatmap, PolarRadial. Use these for full-pane charts,
 * drill-in views, expanded modals, anything where pan/zoom/tooltips matter.
 * Lazy-imported per route — keep them off the Today/Decide hot path.
 *
 * Theme — `./theme/palette.ts` is the single source of truth for chart
 * colors (replaces RatioChart PALETTE + PredictionsByTarget PREDICTION_COLORS
 * + macro-views SECTOR_IDENTITY_HEX). If you add a new chart, pull colors
 * from there.
 *
 * See `.claude/plans/charts-plotly-migration.md` for the migration plan +
 * `.claude/frontend/ui-components.md` "Charts" section for usage rules.
 */

// Tier 1 — SVG primitives
export { Sparkline } from './svg/Sparkline'
export { DriftBar } from './svg/DriftBar'
export type { DriftBarSize } from './svg/DriftBar'
export { MiniCandleCompare } from './svg/MiniCandleCompare'
export type { Ohlc } from './svg/MiniCandleCompare'

// Tier 2 — Plotly
export { PlotlyChart } from './plotly/PlotlyChart'
export type { PlotlyChartProps } from './plotly/PlotlyChart'
export { LineChart } from './plotly/LineChart'
export type { LineChartProps } from './plotly/LineChart'
export { CandlestickChart } from './plotly/CandlestickChart'
export type {
  CandlestickChartProps,
  OhlcBar,
  PredictionSeries,
} from './plotly/CandlestickChart'
export { Heatmap } from './plotly/Heatmap'
export type { HeatmapProps } from './plotly/Heatmap'
export { PolarRadial } from './plotly/PolarRadial'
export type {
  PolarRadialProps,
  PolarQuadrant,
  PolarDot,
} from './plotly/PolarRadial'
export { BumpChart } from './plotly/BumpChart'
export type { BumpChartProps, BumpSeries } from './plotly/BumpChart'

// Tier 3 — ChartBuilder (composable, URL-state-driven multi-pane charts)
export { ChartBuilder } from './builder/ChartBuilder'
export { encodePanes, decodePanes } from './builder/url-state'
export type {
  PaneSpec,
  SeriesSpec,
  ChartType,
  AvailableSeries,
  ResolvedSeries,
} from './builder/types'

// Theme primitives
export * as Palette from './theme/palette'
export * as Tokens from './theme/tokens'
