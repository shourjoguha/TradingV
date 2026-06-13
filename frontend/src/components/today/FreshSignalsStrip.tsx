import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Target, ArrowRight, Sparkle } from 'lucide-react'
import { useOpportunities } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'

const LAST_VISIT_KEY = 'today.last_visited_at'

function readLastVisit(): number {
  if (typeof window === 'undefined') return 0
  const raw = window.localStorage.getItem(LAST_VISIT_KEY)
  const n = raw ? Number(raw) : 0
  return Number.isFinite(n) ? n : 0
}

function writeLastVisit(ts: number): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(LAST_VISIT_KEY, String(ts))
}

/**
 * Fresh Signals strip — opportunities with status='open' that arrived
 * since the operator's last visit to Today.
 *
 * "Last visit" is a localStorage timestamp (`today.last_visited_at`)
 * updated on this component's unmount, so a fresh page load shows the
 * delta since the previous session. New opps are flagged with a sparkle
 * icon. Falls back to showing top 5 open opps if no prior visit.
 */
export function FreshSignalsStrip({ limit = 5 }: { limit?: number }) {
  const { data, isLoading } = useOpportunities({ status: 'open', limit: 50 })

  // Persist last-visit timestamp on unmount only (so the operator sees the
  // delta during this session).
  useEffect(() => {
    return () => {
      writeLastVisit(Date.now())
    }
  }, [])

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Target className="h-4 w-4 text-primary" />
            Fresh Signals
          </CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground italic">
          Loading…
        </CardContent>
      </Card>
    )
  }

  const items = data?.items ?? []
  if (items.length === 0) {
    return (
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Target className="h-4 w-4 text-primary" />
            Fresh Signals
          </CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground italic">
          No open opportunities right now.
        </CardContent>
      </Card>
    )
  }

  const lastVisitMs = readLastVisit()
  const sorted = [...items].sort(
    (a, b) =>
      new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime(),
  )
  const fresh = sorted.filter(
    (o) => new Date(o.generated_at).getTime() > lastVisitMs,
  )
  const display = (fresh.length > 0 ? fresh : sorted).slice(0, limit)
  const freshCount = fresh.length

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Target className="h-4 w-4 text-primary" />
          Fresh Signals
          {freshCount > 0 && (
            <Badge variant="outline" className="ml-1 text-xs">
              {freshCount} new
            </Badge>
          )}
        </CardTitle>
        <Link
          to="/motion/opportunities"
          className="text-xs text-muted-foreground hover:text-primary"
        >
          View all
        </Link>
      </CardHeader>
      <CardContent className="space-y-2">
        {display.map((o) => {
          const isFresh = new Date(o.generated_at).getTime() > lastVisitMs
          return (
            <Link
              key={o.id}
              to="/motion/opportunities"
              className="flex items-center justify-between gap-3 rounded-2xl shadow-inset-sm bg-background px-3 py-2 hover:shadow-extruded-sm transition-all"
            >
              <div className="flex items-baseline gap-2 min-w-0 flex-1">
                {isFresh && <Sparkle className="h-3 w-3 text-primary shrink-0" />}
                <span className="text-sm font-mono font-semibold shrink-0">{o.ticker}</span>
                <Badge
                  variant="outline"
                  className={`text-xs shrink-0 ${
                    o.kind === 'buy'
                      ? 'bg-success-bg text-success-fg'
                      : 'bg-danger-bg text-danger-fg'
                  }`}
                >
                  {o.kind.toUpperCase()}
                </Badge>
                <span
                  className={`text-xs font-mono tabular-nums shrink-0 ${
                    o.predicted_move_pct >= 0 ? 'text-success' : 'text-danger'
                  }`}
                >
                  {o.predicted_move_pct >= 0 ? '+' : ''}
                  {(o.predicted_move_pct * 100).toFixed(2)}%
                </span>
                <span className="text-xs text-muted-foreground truncate min-w-0 flex-1">
                  {o.rule_label || o.rule_id}
                </span>
              </div>
              <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            </Link>
          )
        })}
      </CardContent>
    </Card>
  )
}
