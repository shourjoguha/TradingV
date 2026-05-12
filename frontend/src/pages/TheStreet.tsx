import { useState } from 'react'
import { Building2 } from 'lucide-react'
import { TierTable } from '../components/the-street/TierTable'
import { TickerTimeline } from '../components/the-street/TickerTimeline'
import { SnapshotPicker } from '../components/the-street/SnapshotPicker'

type Mode = 'tiers' | 'ticker' | 'snapshots'

const MODES: Array<{ id: Mode; label: string }> = [
  { id: 'tiers', label: 'Latest tiers' },
  { id: 'ticker', label: 'Ticker timeline' },
  { id: 'snapshots', label: 'Snapshot browser' },
]

/**
 * The Street — universe view of smart-money snapshots stored under
 * `<vault>/The Street/snapshots/`.
 *
 * Three modes (segmented): latest tier 1/2/3 tables, per-ticker timeline
 * across snapshots, and snapshot browser that renders the snapshot's
 * `_index.md` via the vault-indexer node endpoint.
 *
 * Phase 2 of the IA reorg.
 */
export function TheStreet() {
  const [mode, setMode] = useState<Mode>('tiers')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
            <Building2 className="h-6 w-6 text-violet" />
            The Street
          </h2>
          <p className="text-muted-foreground text-sm">
            Smart-money snapshots — institutional 13Fs, insiders, politicians,
            options flow.
          </p>
        </div>
        <div
          role="tablist"
          aria-label="The Street view"
          className="inline-flex rounded-xl bg-background shadow-inset-sm p-1 gap-1"
        >
          {MODES.map((m) => {
            const active = mode === m.id
            return (
              <button
                key={m.id}
                role="tab"
                aria-selected={active}
                onClick={() => setMode(m.id)}
                className={[
                  'px-3 py-1.5 rounded-lg text-xs transition-all',
                  active
                    ? 'bg-card text-foreground shadow-extruded-sm font-medium'
                    : 'text-muted-foreground hover:text-foreground',
                ].join(' ')}
              >
                {m.label}
              </button>
            )
          })}
        </div>
      </div>

      {mode === 'tiers' && (
        <div className="space-y-6">
          <TierTable tier={1} />
          <TierTable tier={2} />
          <TierTable tier={3} />
        </div>
      )}

      {mode === 'ticker' && <TickerTimeline />}

      {mode === 'snapshots' && <SnapshotPicker />}
    </div>
  )
}
