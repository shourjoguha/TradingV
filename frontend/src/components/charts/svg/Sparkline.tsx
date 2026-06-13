/**
 * Sparkline — Tier-1 SVG primitive. Inline-cell line chart for table rows,
 * card widgets, list items. Hand-written `<svg>`; zero chart-library cost.
 *
 * Moved here 2026-05-17 from `components/macro/Sparkline.tsx` as part of
 * Phase 6 of the charts-plotly migration — Tier-1 primitives now live in
 * `components/charts/svg/` so the two-tier infra is colocated.
 *
 * Divide-by-zero bug fixed 2026-05-17 — z-scored series whose `values[0]`
 * landed on or near zero previously returned `Infinity` / `NaN` from the
 * delta-% calc on line 74 of the legacy file. New behaviour: if `first` is
 * within `1e-9` of zero, fall back to an absolute delta in the same units
 * and tag `usesAbsolute=true` so the suffix renders as a unit-less number
 * instead of `%`. Visible only for centered series (Sectors-ladder z-score
 * sparklines); macro-ratio sparklines have non-zero baselines and render
 * identically to before.
 */
import { useMemo } from 'react'
import type { MacroPoint } from '../../../lib/types'
import { SEMANTIC } from '../theme/palette'

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
  const { path, fillPath, delta, usesAbsolute, lineColor } = useMemo(() => {
    const data = weekly ? toWeekly(points) : points
    if (data.length < 2) {
      return {
        path: '',
        fillPath: '',
        delta: null as number | null,
        usesAbsolute: false,
        lineColor: SEMANTIC.neutral,
      }
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

    // Delta calc — guard divide-by-zero. Z-scored series can have `first ≈ 0`,
    // which the legacy code blew up on (`Infinity` / `NaN` cascaded into a
    // broken label render). New behaviour: if `first` is too close to zero
    // to compute a stable percentage, fall back to an absolute delta in the
    // series's own units.
    const first = values[0]
    const last = values[values.length - 1]
    const absDelta = last - first
    let deltaVal: number
    let usesAbs: boolean
    if (Math.abs(first) < 1e-9) {
      deltaVal = absDelta
      usesAbs = true
    } else {
      deltaVal = (absDelta / first) * 100
      usesAbs = false
    }
    // Neumorphic-friendly palette: success / danger from chart theme.
    const color = deltaVal > 0 ? SEMANTIC.success : SEMANTIC.danger

    return {
      path: d,
      fillPath: fill,
      delta: deltaVal,
      usesAbsolute: usesAbs,
      lineColor: color,
    }
  }, [points, width, height, weekly])

  return (
    <div className="flex items-center gap-2 min-w-0">
      {/*
        Responsive SVG: use 100% width + viewBox so the path scales to
        whatever cell it lands in. The width prop still drives the
        coordinate math above (path resolution); the rendered surface
        flexes. preserveAspectRatio='none' lets the path stretch with
        the cell rather than letterbox.
      */}
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        aria-hidden
        className="block flex-1 min-w-0 max-w-full"
        style={{ height }}
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
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>
      {showPct && delta != null && (
        <span
          className="text-xs font-mono tabular-nums whitespace-nowrap shrink-0"
          style={{ color: lineColor }}
        >
          {delta > 0 ? '+' : ''}
          {usesAbsolute ? delta.toFixed(2) : `${delta.toFixed(1)}%`}
        </span>
      )}
    </div>
  )
}
