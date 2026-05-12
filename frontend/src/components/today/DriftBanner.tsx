import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowRight } from 'lucide-react'
import { useDriftAlerts, useAckDriftAlert } from '../../hooks/use-api'
import { Button } from '../ui/button'

/**
 * Drift banner — surfaces unacknowledged drift alerts at the top of Today.
 *
 * Hidden when there are no alerts (does not occupy space). Each alert can
 * be acknowledged inline or opened in the accuracy detail page. Refresh
 * cadence inherits from `useDriftAlerts` (5-minute interval).
 */
export function DriftBanner() {
  const { data, isLoading } = useDriftAlerts()
  const { mutate: ack, isPending: isAcking } = useAckDriftAlert()

  if (isLoading) return null
  const open = (data?.alerts ?? []).filter((a) => !a.acknowledged_at)
  if (open.length === 0) return null

  return (
    <div className="rounded-2xl shadow-extruded-sm bg-warning-bg/60 px-4 py-3 space-y-2">
      <div className="flex items-center gap-2 text-warning-fg text-sm font-medium">
        <AlertTriangle className="h-4 w-4" />
        Drift detected on {open.length} prediction stream{open.length === 1 ? '' : 's'}
      </div>
      <div className="space-y-1.5">
        {open.slice(0, 5).map((a) => (
          <div
            key={a.id}
            className="flex items-center justify-between gap-3 text-xs"
          >
            <div className="font-mono truncate min-w-0 flex-1">
              <span className="font-semibold text-foreground">{a.ticker}</span>
              <span className="text-muted-foreground">
                {' '}h+{a.horizon_offset} · {a.model_id}
              </span>
              <span className="text-warning-fg">
                {' '}· MAPE {Math.round(a.recent_mape * 100)}% (×
                {a.ratio.toFixed(1)} baseline)
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="ghost"
                disabled={isAcking}
                onClick={() => ack(a.id)}
                className="h-7 px-2 text-xs"
              >
                Ack
              </Button>
              <Link
                to="/predictions/accuracy"
                className="text-muted-foreground hover:text-violet"
                aria-label="Open accuracy detail"
              >
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        ))}
        {open.length > 5 && (
          <Link
            to="/predictions/accuracy"
            className="text-xs text-muted-foreground hover:text-violet block pt-1"
          >
            +{open.length - 5} more · open accuracy
          </Link>
        )}
      </div>
    </div>
  )
}
