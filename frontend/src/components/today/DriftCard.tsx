import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowRight } from 'lucide-react'
import { useDriftAlerts } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { InfoBubble } from '../common'

/**
 * Today landing card: drift status preview.
 *
 * Role description survives empty state. Never carries inline action
 * buttons — click-through opens /predictions/accuracy. Ack moved to the
 * detail page to keep landing decision-free.
 *
 * 2026-05-17 density audit: CardDescription promoted to (i)-hover
 * (InfoBubble) — reclaims ~3 lines of vertical space; explainer surfaces
 * only on demand.
 */
export function DriftCard() {
  const { data, isLoading } = useDriftAlerts()
  const open = (data?.alerts ?? []).filter((a) => !a.acknowledged_at)
  const top = open[0]

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle
            className={`h-4 w-4 ${open.length > 0 ? 'text-warning-fg' : 'text-muted-foreground'}`}
          />
          Where it's misfiring
          <InfoBubble
            label="What this means"
            content="Drift = recent MAPE ratio vs all-time per (ticker, horizon). The model flags itself before the operator notices."
          />
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <p className="text-xs text-muted-foreground">Loading…</p>
        ) : open.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No drift alerts in this snapshot. The model is performing within
            its historical baseline.
          </p>
        ) : (
          <div className="space-y-2">
            <div className="flex items-baseline gap-2 text-sm">
              <span className="font-display text-lg font-semibold text-warning-fg">
                {open.length}
              </span>
              <span className="text-xs text-muted-foreground">
                pair{open.length === 1 ? '' : 's'} flagged
              </span>
            </div>
            {top && (
              <div className="font-mono text-xs text-muted-foreground truncate">
                Top: <span className="text-foreground font-semibold">{top.ticker}</span>{' '}
                h+{top.horizon_offset} · MAPE×{top.ratio.toFixed(1)}
              </div>
            )}
            <Link
              to="/predictions/accuracy"
              className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80"
            >
              Open accuracy <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
