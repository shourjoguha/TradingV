/**
 * ChartBuilder — composes N stacked `<Pane>`s. Caller-managed `panes`
 * state so URL persistence + page-level controls stay coordinated.
 *
 * V1 scope (per skeptic review): ratio + series-only panes, line / area /
 * log chart types, multi-series per pane, "+ Add pane" stacks more below.
 * Reusable across future surfaces (PredictionsByTarget enrichment,
 * Hypotheses-evolution chart, etc.) once the abstraction proves out in
 * the Macro Ratios consumer.
 */
import { Plus } from 'lucide-react'
import { Pane } from './Pane'
import type { AvailableSeries, PaneSpec, SeriesSpec } from './types'

interface Props {
  panes: PaneSpec[]
  onChange: (panes: PaneSpec[]) => void
  /** Registry of pickable series for the SeriesPicker per pane. */
  available: AvailableSeries[]
  /** Optional shared `since` window applied to every pane's data hooks. */
  since?: string
  /** Spec template used when "Add pane" is clicked. Defaults to a line
   *  pane with the first available series. */
  defaultNewPane?: () => PaneSpec
}

function defaultNewPaneBuilder(available: AvailableSeries[]): () => PaneSpec {
  return () => {
    const first = available[0]?.build()
    const series: SeriesSpec[] = first
      ? [{ ...first, id: `s_${Math.random().toString(36).slice(2, 8)}` } as SeriesSpec]
      : []
    return {
      id: `p_${Math.random().toString(36).slice(2, 8)}`,
      series,
      chartType: 'line',
    }
  }
}

export function ChartBuilder({
  panes,
  onChange,
  available,
  since,
  defaultNewPane,
}: Props) {
  const addPane = defaultNewPane ?? defaultNewPaneBuilder(available)

  return (
    <div className="space-y-3">
      {panes.map((pane, idx) => (
        <Pane
          key={pane.id}
          pane={pane}
          since={since}
          available={available}
          hideRemove={panes.length === 1}
          onUpdate={(next) => {
            const copy = [...panes]
            copy[idx] = next
            onChange(copy)
          }}
          onRemove={() => {
            onChange(panes.filter((p) => p.id !== pane.id))
          }}
        />
      ))}
      <button
        type="button"
        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-mono bg-background shadow-inset-sm hover:shadow-extruded-sm transition-shadow"
        onClick={() => onChange([...panes, addPane()])}
      >
        <Plus className="h-3.5 w-3.5" />
        Add pane
      </button>
    </div>
  )
}
