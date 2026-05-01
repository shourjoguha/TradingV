import { useMemo } from 'react'
import type { MacroPoint } from '../../lib/types'

interface SparklineProps {
  points: MacroPoint[]
  width?: number
  height?: number
  /**
   * Resample to weekly close — keeps 5y of daily data (~1300 pts) under
   * ~260 SVG line segments. Faster paint + crisper visual at small size.
   */
  weekly?: boolean
  /**
   * Append the trailing Δ% next to the SVG. Default true. Suppress when
   * the host already shows a delta beside the sparkline (avoids two pcts
   * in the same row + overflow on narrow containers).
   */
  showPct?: boolean
}

// Pick last point of each ISO week. Cheap O(n) pass.
function toWeekly(points: MacroPoint[]): MacroPoint[] {
  if (points.length === 0) return []
  const out: MacroPoint[] = []
  let weekKey = ''
  for (const p of points) {
    const d = new Date(p.ts)
    // Year + ISO-ish week number.
    const y = d.getUTCFullYear()
    const start = new Date(Date.UTC(y, 0, 1))
    const week = Math.floor((d.getTime() - start.getTime()) / (7 * 86400_000))
    const k = `${y}-${week}`
    if (k !== weekKey) {
      out.push(p)
      weekKey = k
    } else {
      out[out.length - 1] = p // keep latest within the week
    }
  }
  return out
}

export function Sparkline({
  points,
  width = 120,
  height = 32,
  weekly = true,
  showPct = true,
}: SparklineProps) {
  const { path, fillPath, deltaPct, lineColor } = useMemo(() => {
    const data = weekly ? toWeekly(points) : points
    if (data.length < 2) {
      return { path: '', fillPath: '', deltaPct: null as number | null, lineColor: '#94A3B8' }
    }
    const values = data.map((p) => p.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const span = Math.max(max - min, 1e-9)
    const padX = 1
    const padY = 2
    const innerW = width - padX * 2
    const innerH = height - padY * 2
    const x = (i: number) => padX + (i / (data.length - 1)) * innerW
    const y = (v: number) => padY + (1 - (v - min) / span) * innerH

    let d = `M ${x(0).toFixed(2)} ${y(values[0]).toFixed(2)}`
    for (let i = 1; i < data.length; i++) {
      d += ` L ${x(i).toFixed(2)} ${y(values[i]).toFixed(2)}`
    }
    const fill = `${d} L ${x(data.length - 1).toFixed(2)} ${(height - padY).toFixed(
      2,
    )} L ${x(0).toFixed(2)} ${(height - padY).toFixed(2)} Z`

    const delta = ((values[values.length - 1] - values[0]) / values[0]) * 100
    // Neumorphic-friendly palette: success / danger from tailwind config.
    const color = delta > 0 ? '#5FAFA8' : '#E07A6F'

    return { path: d, fillPath: fill, deltaPct: delta, lineColor: color }
  }, [points, width, height, weekly])

  return (
    <div className="flex items-center gap-2">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden
        className="shrink-0"
      >
        {fillPath && (
          <path d={fillPath} fill={lineColor} fillOpacity="0.12" stroke="none" />
        )}
        {path && (
          <path
            d={path}
            fill="none"
            stroke={lineColor}
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
      </svg>
      {showPct && deltaPct != null && (
        <span
          className="text-[10px] font-mono tabular-nums whitespace-nowrap"
          style={{ color: lineColor }}
        >
          {deltaPct > 0 ? '+' : ''}
          {deltaPct.toFixed(1)}%
        </span>
      )}
    </div>
  )
}
