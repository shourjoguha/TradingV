import { Link } from 'react-router-dom'
import { Stethoscope, AlertTriangle } from 'lucide-react'
import { useRxRecs } from '../hooks/use-api'

/**
 * RxStatusWidget — sidebar ambient pin showing open-rec count.
 *
 * Phase 6 polish (designer P2-9): reduced visual weight so the sidebar
 * stays ambient instead of competing with main content. Same content,
 * tighter padding, smaller type, muted-foreground labels, no shadow.
 *
 * Hidden when nothing is awaiting (operator-respectful no-noise).
 */
export function RxStatusWidget() {
  const { data, isLoading } = useRxRecs({ window_days: 60, limit: 200 })
  if (isLoading || !data) return null
  const eligible = data.items.filter(
    (r) => r.status === 'open' || (r.status === 'snoozed' && r.auto_revived),
  )
  if (eligible.length === 0) return null
  const forced = eligible.filter((r) => r.forced_decision).length

  return (
    <Link
      to="/motion/recs"
      className="mx-3 mb-2 block rounded-xl px-3 py-2 hover:bg-muted/30 transition-all text-xs"
    >
      <div className="flex items-center justify-between text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Stethoscope className="h-3 w-3" />
          <span className="text-xs">recs</span>
        </span>
        <span className="tabular-nums text-foreground font-mono">{eligible.length}</span>
      </div>
      {forced > 0 && (
        <div className="flex items-center justify-between text-danger-fg mt-1">
          <span className="inline-flex items-center gap-1.5">
            <AlertTriangle className="h-3 w-3" />
            <span className="text-xs">forced</span>
          </span>
          <span className="tabular-nums font-mono">{forced}</span>
        </div>
      )}
    </Link>
  )
}
