import { useState } from 'react'
import { useMacroRatio } from '../../hooks/use-api'
import { Sparkline } from './Sparkline'
import { RatioChart } from './RatioChart'
import { SECTOR_ETFS } from '../../lib/macro-views'

interface SectorCellProps {
  symbol: string
  label: string
  since: string
  expanded: boolean
  onClick: () => void
}

function SectorCell({ symbol, label, since, expanded, onClick }: SectorCellProps) {
  const ratio = useMacroRatio({ numerator: symbol, denominator: 'SPY', since })
  const points = ratio.data?.points ?? []
  const first = points[0]?.value
  const last = points[points.length - 1]?.value
  const delta = first && last ? ((last - first) / first) * 100 : null

  // Neumorphic-friendly thresholds. Soft palette.
  let bgClass = 'bg-background shadow-inset-sm text-muted-foreground'
  if (delta != null) {
    if (delta > 1) bgClass = 'bg-success-bg text-success-fg shadow-extruded-sm'
    else if (delta < -1) bgClass = 'bg-danger-bg text-danger-fg shadow-extruded-sm'
    else bgClass = 'bg-warning-bg text-warning-fg shadow-extruded-sm'
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full px-3 py-3 rounded-2xl transition-transform hover:-translate-y-[1px] text-left ${bgClass} ${
        expanded ? 'ring-2 ring-violet/40' : ''
      }`}
      aria-expanded={expanded}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="font-medium text-sm">{label}</span>
        <span className="font-mono text-[10px] opacity-80">{symbol}</span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs tabular-nums">
          {delta == null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%`}
        </span>
        <Sparkline points={points} width={70} height={22} weekly />
      </div>
    </button>
  )
}

interface SectorStripProps {
  since: string
}

export function SectorStrip({ since }: SectorStripProps) {
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null)
  const activeRatio = useMacroRatio({
    numerator: activeSymbol ?? '',
    denominator: 'SPY',
    since,
    enabled: !!activeSymbol,
  })

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 sm:grid-cols-3 lg:grid-cols-9 gap-2">
        {SECTOR_ETFS.map(({ symbol, label }) => (
          <SectorCell
            key={symbol}
            symbol={symbol}
            label={label}
            since={since}
            expanded={activeSymbol === symbol}
            onClick={() => setActiveSymbol((s) => (s === symbol ? null : symbol))}
          />
        ))}
      </div>

      {activeSymbol && (
        <div className="rounded-2xl bg-background shadow-inset-sm p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">
              {activeSymbol} / SPY <span className="text-muted-foreground font-mono text-xs">— relative-strength chart</span>
            </h3>
            <button
              type="button"
              onClick={() => setActiveSymbol(null)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Close
            </button>
          </div>
          {activeRatio.isLoading ? (
            <div className="text-xs text-muted-foreground italic px-2 py-12 text-center">Loading…</div>
          ) : (activeRatio.data?.points.length ?? 0) === 0 ? (
            <div className="text-xs text-muted-foreground italic px-2 py-12 text-center">
              No cached data for this sector.
            </div>
          ) : (
            <RatioChart points={activeRatio.data!.points} height={260} />
          )}
        </div>
      )}
    </div>
  )
}
