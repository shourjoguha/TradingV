/**
 * SeriesPicker — dropdown over an `AvailableSeries[]` registry. Adds the
 * picked series to the pane via `onPick`. Keeps the V1 narrow to a native
 * <select>; can be promoted to a typeahead Combobox later if the registry
 * grows past ~30 entries.
 */
import { useState } from 'react'
import { Plus } from 'lucide-react'
import type { AvailableSeries, SeriesSpec } from './types'

interface Props {
  available: AvailableSeries[]
  /** Already-selected series IDs — hidden from the dropdown to prevent
   *  trivial duplicates. */
  excludeIds?: string[]
  onPick: (spec: Omit<SeriesSpec, 'id'>) => void
}

export function SeriesPicker({ available, excludeIds = [], onPick }: Props) {
  const [open, setOpen] = useState(false)
  const filtered = available.filter((a) => !excludeIds.includes(a.id))
  if (filtered.length === 0) {
    return <span className="text-xs text-muted-foreground italic">All available added</span>
  }
  return (
    <div className="relative inline-block">
      <button
        type="button"
        className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-mono bg-background shadow-inset-sm hover:shadow-extruded-sm transition-shadow"
        onClick={() => setOpen((o) => !o)}
      >
        <Plus className="h-3 w-3" />
        Add series
      </button>
      {open && (
        <div
          className="absolute left-0 top-full mt-1 z-10 max-h-72 w-72 overflow-y-auto rounded-xl bg-card shadow-extruded p-1"
          role="menu"
        >
          {filtered.map((opt) => (
            <button
              type="button"
              key={opt.id}
              className="block w-full text-left px-2 py-1.5 rounded-lg text-xs hover:bg-background"
              onClick={() => {
                onPick(opt.build())
                setOpen(false)
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
