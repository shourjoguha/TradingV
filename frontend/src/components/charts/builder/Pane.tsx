/**
 * Pane — single chart pane inside the ChartBuilder.
 *
 * Resolves all `series` via `useResolvedSeries` (TanStack-cached). Renders
 * via Plotly `<LineChart>` (line / area / log-y modes share the same trace
 * type — area = `fill: 'tozeroy'`, log = `yaxis.type: 'log'`).
 */
import { useMemo } from 'react'
import { X, Trash2 } from 'lucide-react'
import type { Data } from 'plotly.js'
import { PlotlyChart } from '../plotly/PlotlyChart'
import { PREDICTION_LINES } from '../theme/palette'
import { STROKE } from '../theme/tokens'
import { SeriesPicker } from './SeriesPicker'
import { useResolvedSeries } from './use-resolved-series'
import type { AvailableSeries, ChartType, PaneSpec, SeriesSpec } from './types'

interface PaneProps {
  pane: PaneSpec
  since?: string
  available: AvailableSeries[]
  onUpdate: (next: PaneSpec) => void
  onRemove: () => void
  /** When true, hide the remove button (e.g. the only / last pane). */
  hideRemove?: boolean
}

const CHART_TYPE_OPTIONS: Array<{ id: ChartType; label: string }> = [
  { id: 'line', label: 'Line' },
  { id: 'area', label: 'Area' },
  { id: 'log',  label: 'Log Y' },
]

export function Pane({ pane, since, available, onUpdate, onRemove, hideRemove }: PaneProps) {
  const resolved = useResolvedSeries(pane.series, since)
  const isLoading = resolved.some((r) => r.isLoading && r.points.length === 0)

  const data = useMemo<Data[]>(() => {
    return resolved.map((r, idx) => {
      const color = PREDICTION_LINES[idx % PREDICTION_LINES.length]
      const base: Data = {
        type: 'scatter',
        mode: 'lines',
        name: r.label,
        x: r.points.map((p) => p.ts),
        y: r.points.map((p) => p.value),
        line: { color, width: STROKE.primary },
        hovertemplate: `<b>${r.label}</b><br>%{x}<br>%{y:.4f}<extra></extra>`,
      } as Data
      if (pane.chartType === 'area') {
        return { ...base, fill: 'tozeroy', fillcolor: `${color}22` } as Data
      }
      return base
    })
  }, [resolved, pane.chartType])

  const isEmpty = resolved.length === 0 && !isLoading

  const removeSeries = (seriesId: string) => {
    onUpdate({ ...pane, series: pane.series.filter((s) => s.id !== seriesId) })
  }

  const addSeries = (spec: Omit<SeriesSpec, 'id'>) => {
    onUpdate({
      ...pane,
      series: [...pane.series, { ...spec, id: `s_${Math.random().toString(36).slice(2, 8)}` } as SeriesSpec],
    })
  }

  const setChartType = (chartType: ChartType) => {
    onUpdate({ ...pane, chartType })
  }

  return (
    <div className="space-y-2 rounded-2xl bg-background shadow-inset-sm p-3">
      <div className="flex items-center gap-2 flex-wrap">
        {/* Chart-type toggle */}
        <div className="inline-flex rounded-lg bg-card shadow-inset-sm p-0.5 gap-0.5">
          {CHART_TYPE_OPTIONS.map((opt) => {
            const active = opt.id === pane.chartType
            return (
              <button
                key={opt.id}
                type="button"
                className={[
                  'px-2 py-1 rounded-md text-xs transition-all',
                  active
                    ? 'bg-background shadow-extruded-sm font-medium'
                    : 'text-muted-foreground hover:text-foreground',
                ].join(' ')}
                onClick={() => setChartType(opt.id)}
              >
                {opt.label}
              </button>
            )
          })}
        </div>

        {/* Series chips */}
        <div className="flex items-center gap-1 flex-wrap">
          {resolved.map((r) => (
            <span
              key={r.spec.id}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-card text-xs font-mono"
            >
              {r.label}
              <button
                type="button"
                aria-label={`Remove ${r.label}`}
                className="text-muted-foreground hover:text-danger"
                onClick={() => removeSeries(r.spec.id)}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          <SeriesPicker
            available={available}
            excludeIds={pane.series
              .filter((s): s is Extract<SeriesSpec, { kind: 'ratio' }> => s.kind === 'ratio')
              .map((s) => `${s.numerator}/${s.denominator}`)}
            onPick={addSeries}
          />
        </div>

        {/* Remove pane */}
        {!hideRemove && (
          <button
            type="button"
            className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-danger px-2 py-1 rounded-md"
            onClick={onRemove}
            aria-label="Remove pane"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Remove pane
          </button>
        )}
      </div>

      <PlotlyChart
        data={data}
        height={320}
        isLoading={isLoading}
        isEmpty={isEmpty}
        emptyText="Add a series above"
        layout={{
          showlegend: resolved.length > 1,
          legend: {
            orientation: 'h',
            x: 0,
            y: 1.08,
            xanchor: 'left',
            font: { size: 10 },
          },
          yaxis: pane.chartType === 'log' ? { type: 'log' } : undefined,
        }}
      />
    </div>
  )
}
