/**
 * BumpChart — rank-over-time. Each series is rendered as a smoothed line
 * (spline) connecting its rank at each x-axis tick. Y-axis is integer
 * ranks (1 at top) w/ sector symbols on BOTH sides (operator request:
 * left + right mirror, no per-bump labels).
 *
 * Use case: rotation footprint (which sector held rank N at each weekly
 * snapshot). Reusable for any conserved-rank-over-time viz (e.g. cohort
 * leaderboards, sector ETF flows, hypothesis rankings).
 *
 * Matte identity colors come from the chart theme — caller passes
 * `color` per series; recommended source is `IDENTITY.*` from
 * `theme/palette.ts`.
 */
import { useMemo } from 'react'
import type { Data, Layout } from 'plotly.js'
import { PlotlyChart } from './PlotlyChart'
import { SURFACE } from '../theme/palette'

export interface BumpSeries {
  id: string
  label: string
  color: string
  /** Each point is one x-axis tick. `rank` = 1..N (1 strongest). null = missing. */
  points: Array<{ t: string; rank: number | null }>
}

export interface BumpChartProps {
  series: BumpSeries[]
  /** Number of distinct ranks (Y-axis length). Default = `series.length`. */
  rankCount?: number
  height?: number
  isLoading?: boolean
}

export function BumpChart({
  series,
  rankCount,
  height = 320,
  isLoading,
}: BumpChartProps) {
  const N = rankCount ?? series.length

  const data = useMemo<Data[]>(() => {
    return series
      .filter((s) => s.points.length > 0)
      .map((s) => ({
        type: 'scatter',
        mode: 'lines+markers',
        name: s.label,
        x: s.points.map((p) => p.t),
        y: s.points.map((p) => p.rank ?? null),
        connectgaps: false,
        line: {
          color: s.color,
          width: 2,
          shape: 'spline' as const,
          smoothing: 0.8,
        },
        marker: {
          color: s.color,
          size: 6,
          line: { color: '#FFFFFF', width: 1 },
        },
        hovertemplate: `<b>${s.label}</b><br>%{x|%b %d}<br>Rank %{y}<extra></extra>`,
      } as Data))
  }, [series])

  // Build Y-axis tick label dict — rank N → symbols at that rank in the
  // LAST snapshot (rightmost). Used to put labels on right side as well.
  // For the left side we use rank numbers 1..N as ticks.
  const rightLabels = useMemo(() => {
    // Right side: for each rank position, find which series ends there.
    const labelsByRank: Record<number, string> = {}
    for (const s of series) {
      const tail = [...s.points].reverse().find((p) => p.rank != null)
      if (tail?.rank != null) {
        labelsByRank[tail.rank] = s.id
      }
    }
    const out: string[] = []
    for (let r = 1; r <= N; r++) {
      out.push(labelsByRank[r] ?? '')
    }
    return out
  }, [series, N])

  const leftLabels = useMemo(() => {
    const labelsByRank: Record<number, string> = {}
    for (const s of series) {
      const head = s.points.find((p) => p.rank != null)
      if (head?.rank != null && !labelsByRank[head.rank]) {
        labelsByRank[head.rank] = s.id
      }
    }
    const out: string[] = []
    for (let r = 1; r <= N; r++) {
      out.push(labelsByRank[r] ?? '')
    }
    return out
  }, [series, N])

  const tickvals = useMemo(() => Array.from({ length: N }, (_, i) => i + 1), [N])

  const layout = useMemo<Partial<Layout>>(
    () => ({
      margin: { t: 16, r: 56, b: 32, l: 56 },
      showlegend: false,
      xaxis: {
        type: 'date',
        showgrid: false,
        zeroline: false,
      },
      yaxis: {
        autorange: 'reversed', // rank 1 at top
        tickvals,
        ticktext: leftLabels,
        tickfont: { family: '"JetBrains Mono", monospace', size: 11, color: SURFACE.text },
        showgrid: true,
        gridcolor: SURFACE.grid,
        side: 'left',
        zeroline: false,
      },
      // Right-side axis label mirror — overlay yaxis2 with the same range
      // but rightmost ticks showing where each sector landed in the last
      // snapshot.
      yaxis2: {
        autorange: 'reversed',
        tickvals,
        ticktext: rightLabels,
        tickfont: { family: '"JetBrains Mono", monospace', size: 11, color: SURFACE.text },
        side: 'right',
        overlaying: 'y',
        showgrid: false,
        showline: false,
        anchor: 'x',
        matches: 'y',
        zeroline: false,
      },
    }),
    [tickvals, leftLabels, rightLabels],
  )

  const isEmpty = series.length === 0 && !isLoading

  return (
    <PlotlyChart
      data={data}
      height={height}
      isLoading={isLoading}
      isEmpty={isEmpty}
      emptyText="No rank history"
      layout={layout}
    />
  )
}
