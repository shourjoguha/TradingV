/**
 * LineChart — Plotly line chart for time-series. Replaces the
 * lightweight-charts-backed `RatioChart` (Phase 2 of charts-plotly migration).
 *
 * Same prop contract as the legacy RatioChart so callers don't churn:
 *   - `points`        primary series
 *   - `overlay`       optional second series (dashed)
 *   - `height`        chart height in px (default 320)
 *   - `isLoading`     mounts a "Loading…" overlay
 *
 * Visual contract: matches the prior RatioChart palette via `theme/palette.ts`
 * (primary line = identity-liquidity slate-blue, overlay = identity-narrative
 * plum dashed). Hover labels mirror neumorphic card chrome.
 */
import { useMemo } from 'react'
import type { Data } from 'plotly.js'
import { PlotlyChart } from './PlotlyChart'
import type { MacroPoint } from '../../../lib/types'
import { IDENTITY } from '../theme/palette'
import { STROKE } from '../theme/tokens'

export interface LineChartProps {
  points: MacroPoint[]
  height?: number
  overlay?: { points: MacroPoint[]; label?: string }
  isLoading?: boolean
}

export function LineChart({ points, height = 320, overlay, isLoading }: LineChartProps) {
  const data = useMemo<Data[]>(() => {
    const traces: Data[] = []
    if (points.length > 0) {
      traces.push({
        type: 'scatter',
        mode: 'lines',
        name: 'Ratio',
        x: points.map((p) => p.ts),
        y: points.map((p) => p.value),
        line: { color: IDENTITY.liquidity, width: STROKE.primary },
        hovertemplate: '<b>%{x}</b><br>%{y:.4f}<extra></extra>',
      })
    }
    if (overlay && overlay.points.length > 0) {
      traces.push({
        type: 'scatter',
        mode: 'lines',
        name: overlay.label ?? 'Overlay',
        x: overlay.points.map((p) => p.ts),
        y: overlay.points.map((p) => p.value),
        line: {
          color: IDENTITY.narrative,
          width: STROKE.overlay,
          dash: 'dash',
        },
        hovertemplate: '<b>%{x}</b><br>%{y:.4f}<extra></extra>',
      })
    }
    return traces
  }, [points, overlay])

  const isEmpty = points.length === 0 && !isLoading

  return (
    <PlotlyChart
      data={data}
      height={height}
      isLoading={isLoading}
      isEmpty={isEmpty}
      emptyText="No cached data"
      layout={{
        showlegend: !!overlay,
        legend: {
          orientation: 'h',
          x: 0,
          y: 1.08,
          xanchor: 'left',
          font: { size: 10 },
        },
      }}
    />
  )
}
