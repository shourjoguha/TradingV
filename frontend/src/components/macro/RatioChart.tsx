import { useEffect, useRef } from 'react'
import { createChart, type IChartApi, type ISeriesApi, ColorType, LineStyle } from 'lightweight-charts'
import type { MacroPoint } from '../../lib/types'

interface RatioChartProps {
  points: MacroPoint[]
  height?: number
  /**
   * Optional second series for overlaying a comparator line. Used when a
   * caller wants to visually compare two ratios on the same axes.
   */
  overlay?: { points: MacroPoint[]; label?: string }
  isLoading?: boolean
}

// Neumorphic-friendly chart palette. Avoids saturated brand colors so the
// line reads as data, not as a button.
const PALETTE = {
  bg: '#E0E5EC',          // matches body bg in src/index.css
  text: '#3D4852',
  grid: 'rgba(61, 72, 82, 0.08)',
  primary: '#5C8DCC',     // existing accent (used in docs links)
  overlay: '#9F8AC9',
}

export function RatioChart({ points, height = 320, overlay, isLoading }: RatioChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const primarySeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const overlaySeriesRef = useRef<ISeriesApi<'Line'> | null>(null)

  // Mount chart once; resize-aware.
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      autoSize: true,
      height,
      layout: {
        background: { type: ColorType.Solid, color: PALETTE.bg },
        textColor: PALETTE.text,
        fontFamily: 'JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace',
      },
      grid: {
        vertLines: { color: PALETTE.grid, style: LineStyle.Dotted },
        horzLines: { color: PALETTE.grid, style: LineStyle.Dotted },
      },
      timeScale: {
        borderVisible: false,
        secondsVisible: false,
      },
      rightPriceScale: { borderVisible: false },
      crosshair: { mode: 0, vertLine: { color: PALETTE.text, width: 1, style: LineStyle.Dotted } },
    })
    chartRef.current = chart
    primarySeriesRef.current = chart.addLineSeries({
      color: PALETTE.primary,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    })
    return () => {
      chart.remove()
      chartRef.current = null
      primarySeriesRef.current = null
      overlaySeriesRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Push primary data when it changes.
  useEffect(() => {
    const series = primarySeriesRef.current
    if (!series) return
    if (points.length === 0) {
      series.setData([])
      return
    }
    series.setData(
      points.map((p) => ({ time: p.ts as any, value: p.value })),
    )
    chartRef.current?.timeScale().fitContent()
  }, [points])

  // Manage overlay series lifecycle.
  useEffect(() => {
    if (!chartRef.current) return
    if (overlay && overlay.points.length > 0) {
      if (!overlaySeriesRef.current) {
        overlaySeriesRef.current = chartRef.current.addLineSeries({
          color: PALETTE.overlay,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          priceLineVisible: false,
          lastValueVisible: false,
        })
      }
      overlaySeriesRef.current.setData(
        overlay.points.map((p) => ({ time: p.ts as any, value: p.value })),
      )
    } else if (overlaySeriesRef.current) {
      chartRef.current.removeSeries(overlaySeriesRef.current)
      overlaySeriesRef.current = null
    }
  }, [overlay])

  return (
    <div className="relative w-full min-w-0 rounded-2xl bg-background shadow-inset-sm p-2 overflow-hidden">
      <div ref={containerRef} className="min-w-0" style={{ height }} />
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/40 backdrop-blur-[1px] rounded-2xl">
          <span className="text-xs text-muted-foreground">Loading…</span>
        </div>
      )}
    </div>
  )
}
