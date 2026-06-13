import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Target, ArrowRight, Sparkle } from 'lucide-react'
import { useOpportunities } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { InfoBubble } from '../common'

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
 * Today landing card: fresh-signals preview.
 *
 * Shows the count of currently-open opportunities + sparkle count for
 * ones arriving since last visit + a one-line preview of the freshest.
 * Click-through goes to /motion/opportunities for full management.
 */
export function FreshSignalsCard() {
  const { data, isLoading } = useOpportunities({ status: 'open', limit: 50 })

  useEffect(() => {
    return () => writeLastVisit(Date.now())
  }, [])

  const items = data?.items ?? []
  const lastVisitMs = readLastVisit()
  const sorted = [...items].sort(
    (a, b) =>
      new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime(),
  )
  const fresh = sorted.filter((o) => new Date(o.generated_at).getTime() > lastVisitMs)
  const top = sorted[0]

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          <Target className="h-4 w-4 text-primary" />
          What it might pursue
          <InfoBubble
            label="What this means"
            content="Rule-based signals weighted by historical hit-rate. Decision support — operator chooses what to act on."
          />
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <p className="text-xs text-muted-foreground">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No open opportunities. The rules engine is quiet — recheck after
            the next scheduled run.
          </p>
        ) : (
          <div className="space-y-2">
            <div className="flex items-baseline gap-2 text-sm">
              <span className="font-display text-lg font-semibold">{items.length}</span>
              <span className="text-xs text-muted-foreground">
                open
                {fresh.length > 0 && (
                  <>
                    {' '}·{' '}
                    <span className="inline-flex items-center gap-0.5 text-primary">
                      <Sparkle className="h-3 w-3" />
                      {fresh.length} new
                    </span>
                  </>
                )}
              </span>
            </div>
            {top && (
              <div className="font-mono text-xs text-muted-foreground truncate">
                Top:{' '}
                <span className="text-foreground font-semibold">{top.ticker}</span>{' '}
                {top.kind.toUpperCase()}{' '}
                <span
                  className={
                    top.predicted_move_pct >= 0 ? 'text-success' : 'text-danger'
                  }
                >
                  {top.predicted_move_pct >= 0 ? '+' : ''}
                  {(top.predicted_move_pct * 100).toFixed(2)}%
                </span>
              </div>
            )}
            <Link
              to="/motion/opportunities"
              className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80"
            >
              Open signals <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
