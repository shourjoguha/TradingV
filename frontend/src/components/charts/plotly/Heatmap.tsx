/**
 * Heatmap — Plotly 2D heatmap. Replaces the bespoke HTML-table
 * `CorrelationHeatmap` render path (Phase 5 of charts-plotly migration).
 *
 * Operator's use: 9×9 pairwise correlation of daily log-returns. Cells
 * tinted from red (-1) → grey (0) → green (+1) via `CORRELATION_GRADIENT`
 * from the chart theme. Diagonal pinned (set to NaN in input or skipped
 * via z=[[null,...],[...,null]] pattern; we leave the value but render
 * it as "1" w/ no special diagonal styling — Plotly hover handles it).
 */
import { useMemo, useState, useCallback } from 'react'
import type { Data, ColorScale, PlotMouseEvent } from 'plotly.js'
import { PlotlyChart } from './PlotlyChart'
import { CORRELATION_GRADIENT } from '../theme/palette'

export interface HeatmapProps {
  /** Row labels (top → bottom of the rendered chart). */
  rows: string[]
  /** Column labels (left → right). */
  cols: string[]
  /**
   * 2D array of values. `z[r][c]` is the cell at row `r`, col `c`.
   * Values outside [-1, +1] are clamped by the colorscale; NaN renders blank.
   */
  z: number[][]
  /** Optional gradient override (default = correlation red→grey→green). */
  colorscale?: ColorScale
  /** Min value mapped to gradient stop 0. Default -1. */
  zmin?: number
  /** Max value mapped to gradient stop 1. Default +1. */
  zmax?: number
  /** Hover template (Plotly format string). Default shows row/col/value. */
  hovertemplate?: string
  height?: number
  isLoading?: boolean
  /**
   * Fired when a data cell is clicked. `value` is the z-value at the
   * intersection; `row` / `col` are the corresponding label strings.
   * Use the click target to drive a drill-in (e.g. rolling correlation).
   */
  onCellClick?: (row: string, col: string, value: number) => void
}

export function Heatmap({
  rows,
  cols,
  z,
  colorscale = CORRELATION_GRADIENT as unknown as ColorScale,
  zmin = -1,
  zmax = 1,
  hovertemplate = '<b>%{y} vs %{x}</b><br>%{z:.2f}<extra></extra>',
  height = 380,
  isLoading,
  onCellClick,
}: HeatmapProps) {
  const data = useMemo<Data[]>(() => {
    if (rows.length === 0 || cols.length === 0) return []
    return [
      {
        type: 'heatmap',
        x: cols,
        y: rows,
        z,
        zmin,
        zmax,
        colorscale,
        showscale: true,
        colorbar: {
          thickness: 8,
          len: 0.8,
          tickfont: { size: 10 },
        },
        hovertemplate,
        // Plotly renders text labels per-cell when `text` is provided. Use the
        // 2dp value as the label so the visual matches the old HTML table.
        // `text` for heatmap accepts 2D arrays at runtime, but
        // `@types/plotly.js` only types 1D. Cast through unknown.
        text: z.map((row) => row.map((v) => (Number.isFinite(v) ? v.toFixed(2) : '—'))) as unknown as string[],
        texttemplate: '%{text}',
        textfont: { size: 10, family: '"JetBrains Mono", monospace' },
      } as unknown as Data,
    ]
  }, [rows, cols, z, colorscale, zmin, zmax, hovertemplate])

  const isEmpty = rows.length === 0 && !isLoading

  const handleClick = useCallback(
    (e: Readonly<PlotMouseEvent>) => {
      if (!onCellClick) return
      const pt = e.points?.[0]
      if (!pt) return
      const x = typeof pt.x === 'string' ? pt.x : String(pt.x)
      const y = typeof pt.y === 'string' ? pt.y : String(pt.y)
      const v = (pt as { z?: number }).z
      if (typeof v !== 'number') return
      onCellClick(y, x, v)
    },
    [onCellClick],
  )

  return (
    <PlotlyChart
      data={data}
      height={height}
      isLoading={isLoading}
      isEmpty={isEmpty}
      emptyText="No correlation data"
      layout={{
        margin: { t: 8, r: 8, b: 32, l: 48 },
        xaxis: { side: 'top', tickfont: { size: 10 } },
        yaxis: { autorange: 'reversed' /* match the HTML table's top-down read */ },
      }}
      onClick={onCellClick ? handleClick : undefined}
    />
  )
}
