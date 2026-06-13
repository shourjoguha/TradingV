/**
 * PlotlyChart — base wrapper around `react-plotly.js/factory` w/ neumorphic
 * theme injected + ResizeObserver + loading/empty states.
 *
 * Tier-2 charts in the two-tier infra (Tier 1 = inline SVG primitives in
 * `../svg/`). Lazy-loaded by route — never imported in Today / DriftBar etc.
 *
 * Callers pass `data` + an optional layout/config that's deep-merged with
 * `BASE_LAYOUT` / `BASE_CONFIG`. The factory uses our custom plotly bundle
 * so only registered trace types are shipped.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Data, Layout, Config, PlotMouseEvent } from 'plotly.js'
import createPlotlyComponent from 'react-plotly.js/factory'
import { ensurePlotlyRegistered } from '../plotly-bundle'
import { BASE_LAYOUT, BASE_CONFIG } from '../theme/layout'

// Build the React wrapper from the custom (registered) Plotly instance.
const Plot = createPlotlyComponent(ensurePlotlyRegistered())

export interface PlotlyChartProps {
  data: Data[]
  layout?: Partial<Layout>
  config?: Partial<Config>
  height?: number
  /** Show a centered loading hint over a neumorphic placeholder. */
  isLoading?: boolean
  /** When true, render an empty-state hint instead of an empty chart. */
  isEmpty?: boolean
  /** Empty-state text. Defaults to "No data". */
  emptyText?: string
  /** className passed to the outer card. */
  className?: string
  /** Plotly click event passthrough — fired on data-point clicks. */
  onClick?: (e: Readonly<PlotMouseEvent>) => void
}

/** Shallow-merge layout overrides while preserving nested defaults. */
function mergeLayout(extra: Partial<Layout> | undefined, height: number): Partial<Layout> {
  return {
    ...BASE_LAYOUT,
    ...extra,
    height,
    xaxis: { ...BASE_LAYOUT.xaxis, ...extra?.xaxis },
    yaxis: { ...BASE_LAYOUT.yaxis, ...extra?.yaxis },
    hoverlabel: { ...BASE_LAYOUT.hoverlabel, ...extra?.hoverlabel },
    font: { ...BASE_LAYOUT.font, ...extra?.font },
    margin: { ...BASE_LAYOUT.margin, ...extra?.margin },
  }
}

export function PlotlyChart({
  data,
  layout,
  config,
  height = 320,
  isLoading,
  isEmpty,
  emptyText = 'No data',
  className,
  onClick,
}: PlotlyChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [width, setWidth] = useState<number>(600)

  // Observe container size — Plotly's autosize is unreliable inside flex/grid.
  useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (w && Math.abs(w - width) > 1) setWidth(w)
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const mergedLayout = useMemo<Partial<Layout>>(
    () => ({ ...mergeLayout(layout, height), width }),
    [layout, height, width],
  )
  const mergedConfig = useMemo<Partial<Config>>(
    () => ({ ...BASE_CONFIG, ...config }),
    [config],
  )

  return (
    <div
      ref={containerRef}
      className={[
        'relative w-full min-w-0 rounded-2xl bg-background shadow-inset-sm p-2 overflow-hidden',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      style={{ height: height + 16 /* match p-2 + padding */ }}
    >
      {isEmpty ? (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground italic">
          {emptyText}
        </div>
      ) : (
        <Plot
          data={data}
          layout={mergedLayout}
          config={mergedConfig}
          useResizeHandler={false /* we drive width via ResizeObserver */}
          style={{ width: '100%', height: '100%' }}
          onClick={onClick}
        />
      )}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/40 backdrop-blur-[1px] rounded-2xl">
          <span className="text-xs text-muted-foreground">Loading…</span>
        </div>
      )}
    </div>
  )
}
