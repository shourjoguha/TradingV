/**
 * MiniCandleCompare — Tier-1 SVG primitive. Side-by-side actual-vs-predicted
 * mini-candle pair w/ sparse reference labels (actual close, predicted high,
 * predicted low). Used per-cell in the Predictions-by-Horizon matrix.
 *
 * Extracted 2026-05-17 from `pages/PredictionsByHorizon.tsx` as part of
 * Phase 6 of the charts-plotly migration — Tier-1 primitives now live in
 * `components/charts/svg/` so the two-tier infra is colocated.
 *
 * Behavior unchanged. Uses Tailwind `stroke-success` / `fill-success` etc.
 * to inherit the design-system semantic palette (no hex literals inline).
 */
export type Ohlc = {
  open?: number
  high?: number
  low?: number
  close?: number
  volume?: number
}

export function MiniCandleCompare({
  actual,
  predicted,
}: {
  actual: Ohlc | null
  predicted: Ohlc | null
}) {
  const vals = [actual?.high, actual?.low, predicted?.high, predicted?.low].filter(
    (v): v is number => typeof v === 'number',
  )
  if (vals.length === 0) return <div className="text-xs text-muted-foreground">no data</div>
  const max = Math.max(...vals)
  const min = Math.min(...vals)
  const span = Math.max(max - min, 1e-6)
  const W = 160
  const H = 90
  const pad = 14
  const innerH = H - pad * 2
  const y = (v: number) => pad + (1 - (v - min) / span) * innerH

  const candle = (o: Ohlc | null, x: number, label: string) => {
    if (!o || o.open == null || o.high == null || o.low == null || o.close == null) {
      return (
        <g>
          <text x={x} y={H - 2} textAnchor="middle" fontSize="9" className="fill-muted-foreground">
            {label}
          </text>
        </g>
      )
    }
    const up = o.close >= o.open
    const fill = up ? 'fill-success' : 'fill-danger'
    const stroke = up ? 'stroke-success' : 'stroke-danger'
    const bodyTop = Math.min(y(o.open), y(o.close))
    const bodyBot = Math.max(y(o.open), y(o.close))
    const bodyH = Math.max(bodyBot - bodyTop, 1.5)
    return (
      <g>
        <line x1={x} x2={x} y1={y(o.high)} y2={y(o.low)} className={stroke} strokeWidth={1.2} />
        <rect x={x - 8} y={bodyTop} width={16} height={bodyH} className={fill} rx={1.5} />
        <text x={x} y={H - 2} textAnchor="middle" fontSize="9" className="fill-muted-foreground">
          {label}
        </text>
      </g>
    )
  }

  // 3 sparse refs: actual.close, predicted.high, predicted.low
  const refs: {
    v: number | undefined
    x: number
    y: number
    anchor: 'start' | 'end'
    label: string
  }[] = [
    {
      v: actual?.close,
      x: 36,
      y: actual?.close != null ? y(actual.close) : 0,
      anchor: 'end',
      label: actual?.close != null ? `$${actual.close.toFixed(2)}` : '',
    },
    {
      v: predicted?.high,
      x: W - 36,
      y: predicted?.high != null ? y(predicted.high) : 0,
      anchor: 'start',
      label: predicted?.high != null ? `H $${predicted.high.toFixed(2)}` : '',
    },
    {
      v: predicted?.low,
      x: W - 36,
      y: predicted?.low != null ? y(predicted.low) : 0,
      anchor: 'start',
      label: predicted?.low != null ? `L $${predicted.low.toFixed(2)}` : '',
    },
  ]
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      className="font-mono max-w-full h-auto"
    >
      {candle(actual, 40, 'Actual')}
      {candle(predicted, W - 40, 'Predicted')}
      {refs.map((r, i) =>
        r.v == null ? null : (
          <text
            key={i}
            x={r.x}
            y={r.y + 3}
            textAnchor={r.anchor}
            fontSize="9"
            className="fill-foreground"
          >
            {r.label}
          </text>
        ),
      )}
    </svg>
  )
}
