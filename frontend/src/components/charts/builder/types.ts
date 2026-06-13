/**
 * ChartBuilder primitive — public types.
 *
 * V1 scope (deliberately narrow per skeptic review): ratio series only,
 * chart types = line / area / log. Spreads, OHLC, heatmaps deferred until
 * a 2nd consumer surface demands them.
 */
import type { MacroPoint } from '../../../lib/types'

/** Chart types V1 supports. */
export type ChartType = 'line' | 'area' | 'log'

/** A single series the builder can resolve through cached hooks. */
export type SeriesSpec =
  | {
      kind: 'ratio'
      /** Stable id; used as React key + URL fragment. */
      id: string
      numerator: string
      denominator: string
      /** Display label shown in legend / picker. Falls back to "NUM/DEN". */
      label?: string
    }
  | {
      kind: 'series'
      id: string
      symbol: string
      label?: string
    }

/** A pane = one chart w/ N series. */
export interface PaneSpec {
  id: string
  series: SeriesSpec[]
  chartType: ChartType
}

/** Registry entry — what a `SeriesPicker` shows as an option. */
export interface AvailableSeries {
  id: string
  /** Display label. */
  label: string
  /** When picked, builds this spec (minus id which the builder assigns). */
  build: () => Omit<SeriesSpec, 'id'>
}

/** Resolved (data-fetched) series the chart consumes. */
export interface ResolvedSeries {
  spec: SeriesSpec
  label: string
  points: MacroPoint[]
  isLoading: boolean
  isError: boolean
}
