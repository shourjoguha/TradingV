import { Link } from 'react-router-dom'
import { Clock, Stethoscope, ChevronRight } from 'lucide-react'
import { useRxRecs } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { DriftBar } from '../charts/svg/DriftBar'
import { StatusBadge } from '../common/StatusBadge'

/**
 * Today strip — top-N open finance recs needing decision.
 *
 * Operator-respectful empty-state pattern: hidden entirely when there
 * are no open recs. Surfaces the morning question: "anything urgent the
 * generator flagged since I last looked?"
 *
 * Ranking: aging > forced-decision > drift_score desc. Forced-decision
 * (snooze_count >= 2) outranks plain aging so the operator can't keep
 * snoozing past the threshold without seeing the chip.
 */
const VISIBLE_CAP = 3

function relTime(iso: string): string {
  const now = Date.now()
  const t = new Date(iso).getTime()
  const ago = Math.max(0, now - t)
  const min = Math.floor(ago / 60_000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const d = Math.floor(hr / 24)
  return `${d}d ago`
}

export function RxStrip() {
  // Window=60d matches the rec-list default; only `open` + auto-revived
  // `snoozed` rows are actionable for the morning glance.
  const recs = useRxRecs({ window_days: 60, limit: 50 })
  if (recs.isLoading) return null
  const all = recs.data?.items ?? []
  // Eligible = open OR snoozed-past-its-window.
  const eligible = all.filter(
    (r) => r.status === 'open' || (r.status === 'snoozed' && r.auto_revived),
  )
  if (eligible.length === 0) return null

  // Sort: forced first, then aging, then by drift_score desc.
  const sorted = [...eligible].sort((a, b) => {
    if (a.forced_decision !== b.forced_decision) {
      return a.forced_decision ? -1 : 1
    }
    if (a.aging !== b.aging) return a.aging ? -1 : 1
    return (b.drift_score ?? 0) - (a.drift_score ?? 0)
  })
  const visible = sorted.slice(0, VISIBLE_CAP)
  const overflow = sorted.length - visible.length

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Stethoscope className="h-4 w-4 text-primary" />
          Open recommendations
          <Badge variant="outline" className="ml-2 text-xs">
            {sorted.length}
          </Badge>
        </CardTitle>
        <Link
          to="/motion/recs"
          className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
        >
          All recs <ChevronRight className="h-3 w-3" />
        </Link>
      </CardHeader>
      <CardContent className="space-y-2">
        {visible.map((r) => (
          <Link
            key={r.id}
            to={`/motion/recs/${r.id}`}
            className="flex items-center gap-3 rounded-2xl px-3 py-2 hover:bg-muted/40 transition-all"
          >
            <span className="font-mono text-xs text-muted-foreground w-16 shrink-0">
              {r.short_id}
            </span>
            <DriftBar score={r.drift_score} size="sm" />
            <span className="flex-1 text-sm truncate">
              {r.tldr_short || <span className="text-muted-foreground italic">no tldr</span>}
            </span>
            <span className="flex items-center gap-1 shrink-0">
              {r.forced_decision && <StatusBadge kind="flag" value="forced" size="xs" />}
              {r.auto_revived && <StatusBadge kind="flag" value="revived" size="xs" />}
              {/* Single temporal info source: relative time. The aging
                  flag is reflected in the colored chip when it's the
                  dominant ranking signal. */}
              <span
                className={`text-xs whitespace-nowrap tabular-nums ${
                  r.aging ? 'text-amber-700 font-medium' : 'text-muted-foreground'
                }`}
                title={r.aging ? `aging — open ${r.age_days}d` : undefined}
              >
                {r.aging ? <Clock className="h-3 w-3 mr-1 inline" /> : null}
                {relTime(r.created_at)}
              </span>
            </span>
          </Link>
        ))}
        {overflow > 0 && (
          <Link
            to="/motion/recs"
            className="block text-xs text-muted-foreground hover:text-foreground pt-1 pl-3"
          >
            +{overflow} more →
          </Link>
        )}
      </CardContent>
    </Card>
  )
}
