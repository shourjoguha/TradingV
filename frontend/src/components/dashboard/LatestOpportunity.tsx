import { Link } from 'react-router-dom'
import { useOpportunities } from '../../hooks/use-api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Target, ArrowRight } from 'lucide-react'

export function LatestOpportunity() {
  const { data, isLoading } = useOpportunities({ status: 'open', limit: 1 })
  const opp = data?.items?.[0]

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Target className="h-4 w-4 text-violet" />
          Latest Opportunity
        </CardTitle>
        <Link
          to="/motion/opportunities"
          className="text-xs text-muted-foreground hover:text-violet"
        >
          View all
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground italic">Loading…</div>
        ) : !opp ? (
          <div className="text-sm text-muted-foreground italic">
            No open opportunities right now.
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="text-xl font-mono font-semibold">{opp.ticker}</span>
              <Badge
                variant="outline"
                className={
                  opp.kind === 'buy'
                    ? 'bg-success-bg text-success-fg'
                    : 'bg-danger-bg text-danger-fg'
                }
              >
                {opp.kind.toUpperCase()}
              </Badge>
              <span
                className={`text-sm font-mono tabular-nums ${
                  opp.predicted_move_pct >= 0 ? 'text-success' : 'text-danger'
                }`}
              >
                {opp.predicted_move_pct >= 0 ? '+' : ''}
                {(opp.predicted_move_pct * 100).toFixed(2)}%
              </span>
              <span className="text-xs text-muted-foreground">
                conf {(opp.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <CardDescription className="text-xs">
              Rule: <span className="font-mono">{opp.rule_label || opp.rule_id}</span>
              {opp.expires_at && (
                <> · expires {new Date(opp.expires_at).toLocaleDateString()}</>
              )}
            </CardDescription>
            <div>
              <Button size="sm" asChild>
                <Link to="/motion/opportunities">
                  Review <ArrowRight className="ml-1 h-3 w-3" />
                </Link>
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
