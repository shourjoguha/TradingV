/**
 * CandlestickChart — Plotly candlestick + optional N overlay lines. Replaces
 * the lightweight-charts `createChart` block in `PredictionsByTarget.tsx`
 * (Phase 3 of charts-plotly migration, 2026-05-17).
 *
 * Operator's use: actual OHLC candles + N prediction lines color-coded by
 * `days_ago`. Lines anchor at the target date; for multi-prediction days,
 * we plot one marker per made_on date.
 */
import { useMemo } from 'react'
import type { Data } from 'plotly.js'
import { PlotlyChart } from './PlotlyChart'
import { CANDLE, PREDICTION_LINES } from '../theme/palette'
import { STROKE } from '../theme/tokens'

export interface OhlcBar {
  time: string
  open: number
  high: number
  low: number
  close: number
}

/**
 * One prediction series. For a single-prediction case (one made_on, one
 * target_date), the line connects (made_on → target_date) at the predicted
 * close. For multi-prediction days, supply multiple x/y points.
 */
export interface PredictionSeries {
  /** Label shown in legend + hover, e.g. "T-1" / "T-5". */
  label: string
  /** Time-domain x-axis values (ISO date strings). */
  x: string[]
  /** Numeric y values (predicted close). */
  y: number[]
}

export interface CandlestickChartProps {
  bars: OhlcBar[]
  predictions?: PredictionSeries[]
  height?: number
  isLoading?: boolean
}

export function CandlestickChart({
  bars,
  predictions = [],
  height = 320,
  isLoading,
}: CandlestickChartProps) {
  const data = useMemo<Data[]>(() => {
    const traces: Data[] = []
    if (bars.length > 0) {
      const sorted = [...bars].sort((a, b) => (a.time < b.time ? -1 : 1))
      // Cast: `@types/plotly.js` Candlestick spec omits `fillcolor` though
      // Plotly accepts it at runtime (per Plotly JSON schema).
      traces.push({
        type: 'candlestick',
        name: 'OHLC',
        x: sorted.map((b) => b.time),
        open: sorted.map((b) => b.open),
        high: sorted.map((b) => b.high),
        low: sorted.map((b) => b.low),
        close: sorted.map((b) => b.close),
        increasing: { line: { color: CANDLE.up }, fillcolor: CANDLE.up } as never,
        decreasing: { line: { color: CANDLE.down }, fillcolor: CANDLE.down } as never,
        showlegend: false,
      } as Data)
    }
    predictions.forEach((p, idx) => {
      if (p.x.length === 0) return
      const color = PREDICTION_LINES[idx % PREDICTION_LINES.length]
      // Single-point predictions render as markers (no line to draw).
      const mode = p.x.length === 1 ? 'markers' : 'lines+markers'
      traces.push({
        type: 'scatter',
        mode,
        name: p.label,
        x: p.x,
        y: p.y,
        line: { color, width: STROKE.primary },
        marker: { color, size: 6 },
        hovertemplate: `<b>${p.label}</b><br>%{x}<br>%{y:.2f}<extra></extra>`,
      })
    })
    return traces
  }, [bars, predictions])

  const isEmpty = bars.length === 0 && !isLoading

  return (
    <PlotlyChart
      data={data}
      height={height}
      isLoading={isLoading}
      isEmpty={isEmpty}
      emptyText="No OHLC data"
      layout={{
        showlegend: false /* prediction legend rendered separately in caller header */,
        xaxis: { rangeslider: { visible: false }, type: 'category' },
      }}
    />
  )
}
