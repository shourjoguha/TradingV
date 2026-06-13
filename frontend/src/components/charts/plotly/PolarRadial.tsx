/**
 * PolarRadial — Plotly polar chart for cycle / RRG / radar viz. Composition:
 *
 *   - `quadrants`  array of `{ startDeg, endDeg, color, alpha, label, active }`
 *                  → rendered via `barpolar` (one bar per quadrant w/ full radius)
 *   - `dots`       array of `{ theta, r, size, color, label, hover }`
 *                  → rendered via `scatterpolar` markers + text labels
 *   - `centerText` optional 1-2 line label rendered as a center annotation
 *
 * Replaces the bespoke SVG `CyclePhaseWheel` (Phase 5 of charts-plotly
 * migration). Same data contract, native pan/hover/click, opens the path to
 * future RRG-style continuous trails (just pass `dots` w/ historical
 * snapshots as a scatterpolar `lines+markers` trace).
 *
 * NOTE: Plotly polar uses angle in degrees measured COUNTER-clockwise from
 * 3 o'clock (East). The CyclePhaseWheel data uses clockwise-from-12-o'clock
 * (North). Conversion: `plotlyAngle = 90 - clockwiseFromNorth`.
 */
import { useMemo } from 'react'
import type { Data, Layout } from 'plotly.js'
import { PlotlyChart } from './PlotlyChart'
import { SURFACE } from '../theme/palette'

/** Convert clockwise-from-12 (operator's mental model) → Plotly polar deg. */
export function ccwAngle(clockwiseFromNorthDeg: number): number {
  return (90 - clockwiseFromNorthDeg + 360) % 360
}

export interface PolarQuadrant {
  startDeg: number // clockwise from 12 o'clock
  endDeg: number   // clockwise from 12 o'clock
  color: string    // hex fill for this quadrant
  alpha?: number   // 0..1 fill opacity (default 0.08)
  label?: string   // displayed at outer mid-angle
  active?: boolean // when true, fill renders at full alpha + bold label
}

export interface PolarDot {
  theta: number   // clockwise from 12 o'clock
  r: number       // 0..1 (fraction of plot radius)
  size: number    // marker size in px
  color: string   // fill hex
  label?: string  // text shown next to the dot
  hover?: string  // hover-template content (no HTML)
}

export interface PolarRadialProps {
  quadrants: PolarQuadrant[]
  dots: PolarDot[]
  centerText?: { primary: string; secondary?: string }
  /** Outer radius in chart units. Default 1 (so dot `r` is in [0,1]). */
  radius?: number
  height?: number
  isLoading?: boolean
}

export function PolarRadial({
  quadrants,
  dots,
  centerText,
  radius = 1,
  height = 400,
  isLoading,
}: PolarRadialProps) {
  const data = useMemo<Data[]>(() => {
    const traces: Data[] = []

    // Quadrants as barpolar bars. Each bar spans `endDeg - startDeg` width
    // centered on the midpoint angle, w/ height = radius (full).
    if (quadrants.length > 0) {
      // Active first as a separate trace so its opacity overrides correctly.
      const inactive = quadrants.filter((q) => !q.active)
      const active = quadrants.filter((q) => q.active)

      const buildBar = (qs: PolarQuadrant[], baseAlpha: number): Data => {
        const theta: number[] = []
        const width: number[] = []
        const colors: string[] = []
        for (const q of qs) {
          const widthDeg = q.endDeg - q.startDeg
          const midClockwise = (q.startDeg + q.endDeg) / 2
          theta.push(ccwAngle(midClockwise))
          width.push(widthDeg)
          colors.push(q.color)
        }
        return {
          type: 'barpolar',
          r: qs.map(() => radius),
          theta,
          width,
          marker: {
            color: colors,
            opacity: baseAlpha,
            line: { width: 0 },
          },
          hoverinfo: 'skip',
          showlegend: false,
        } as Data
      }

      if (inactive.length > 0) traces.push(buildBar(inactive, 0.06))
      if (active.length > 0) traces.push(buildBar(active, 0.22))
    }

    // Dots — one scatterpolar trace, markers + text.
    if (dots.length > 0) {
      // Cast: `@types/plotly.js` mode union excludes 'markers+text' for the
      // narrow Scatter type — runtime accepts it on scatterpolar.
      traces.push({
        type: 'scatterpolar',
        mode: 'markers+text' as never,
        r: dots.map((d) => d.r),
        theta: dots.map((d) => ccwAngle(d.theta)),
        marker: {
          size: dots.map((d) => d.size),
          color: dots.map((d) => d.color),
          line: { color: '#FFFFFF', width: 1.5 },
          opacity: 0.9,
        },
        text: dots.map((d) => d.label ?? ''),
        textfont: { size: 9, family: '"JetBrains Mono", monospace', color: SURFACE.text },
        textposition: 'top center',
        hovertemplate: dots.map((d) => d.hover ?? d.label ?? '').map((s) => `${s}<extra></extra>`),
        showlegend: false,
      } as Data)
    }

    return traces
  }, [quadrants, dots, radius])

  // Quadrant outer labels + optional center text → Plotly annotations.
  const annotations = useMemo<Layout['annotations']>(() => {
    const out: NonNullable<Layout['annotations']> = []
    for (const q of quadrants) {
      if (!q.label) continue
      const midClockwise = (q.startDeg + q.endDeg) / 2
      // Place label just outside the radius. Plotly polar uses `xref:'paper'`
      // and `yref:'paper'` for annotations w/ x/y in [0,1], OR (preferred)
      // use polar mode w/ `xref:'x'`, but polar annotations need different
      // refs. Simpler: convert to paper-space cartesian centered at (0.5, 0.5).
      const angleRad = (ccwAngle(midClockwise) * Math.PI) / 180
      const labelR = 0.52 // outside the plot area, well inside the panel
      const px = 0.5 + labelR * Math.cos(angleRad)
      const py = 0.5 + labelR * Math.sin(angleRad)
      out.push({
        x: px,
        y: py,
        xref: 'paper',
        yref: 'paper',
        text: q.label,
        showarrow: false,
        font: {
          size: 11,
          color: q.active ? SURFACE.text : SURFACE.textMuted,
          family: '"DM Sans", system-ui, sans-serif',
        },
        align: 'center',
      })
    }
    if (centerText) {
      out.push({
        x: 0.5,
        y: 0.52,
        xref: 'paper',
        yref: 'paper',
        text: centerText.primary,
        showarrow: false,
        font: { size: 18, color: SURFACE.text, family: '"DM Sans", system-ui, sans-serif' },
      })
      out.push({
        x: 0.5,
        y: 0.46,
        xref: 'paper',
        yref: 'paper',
        text: 'you are here',
        showarrow: false,
        font: { size: 10, color: SURFACE.textMuted },
      })
      if (centerText.secondary) {
        out.push({
          x: 0.5,
          y: 0.42,
          xref: 'paper',
          yref: 'paper',
          text: centerText.secondary,
          showarrow: false,
          font: { size: 10, color: SURFACE.textMuted, family: '"JetBrains Mono", monospace' },
        })
      }
    }
    return out
  }, [quadrants, centerText])

  return (
    <PlotlyChart
      data={data}
      height={height}
      isLoading={isLoading}
      isEmpty={quadrants.length === 0 && dots.length === 0 && !isLoading}
      layout={{
        margin: { t: 24, r: 24, b: 24, l: 24 },
        polar: {
          bgcolor: SURFACE.bg,
          radialaxis: {
            visible: false,
            range: [0, radius],
          },
          angularaxis: {
            visible: false,
            rotation: 0,
            direction: 'counterclockwise',
          },
        },
        annotations,
        showlegend: false,
      }}
    />
  )
}
