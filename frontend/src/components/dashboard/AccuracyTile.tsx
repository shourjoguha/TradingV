import { Link } from 'react-router-dom'
import { useAccuracyGrid } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Activity } from 'lucide-react'

// Rolls the last-30-day grid into a single read: average hit-rate, average
// MAPE, total samples. Operator's "is the model working overall?" answer.
export function AccuracyTile() {
  const { data, isLoading } = useAccuracyGrid({ last_n: 30 })
  const rows = data?.rows ?? []

  let totalN = 0
  let weightedHit = 0
  let weightedMape = 0
  for (const r of rows) {
    if (r.hit_rate != null && r.sample_count > 0) {
      totalN += r.sample_count
      weightedHit += r.hit_rate * r.sample_count
      weightedMape += r.mape * r.sample_count
    }
  }
  const avgHit = totalN > 0 ? weightedHit / totalN : null
  const avgMape = totalN > 0 ? weightedMape / totalN : null

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Activity className="h-4 w-4 text-violet" />
          Accuracy (30d)
        </CardTitle>
        <Link
          to="/predictions/accuracy"
          className="text-xs text-muted-foreground hover:text-violet"
        >
          Detail
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground italic">Loading…</div>
        ) : totalN === 0 ? (
          <div className="text-sm text-muted-foreground italic">
            No evaluated predictions yet.
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-mono font-semibold tabular-nums">
                {avgHit != null ? `${(avgHit * 100).toFixed(0)}%` : '—'}
              </span>
              <span className="text-sm text-muted-foreground font-mono">
                / {avgMape != null ? `${(avgMape * 100).toFixed(1)}%` : '—'} MAPE
              </span>
            </div>
            <div className="text-[11px] font-mono text-muted-foreground">
              {totalN.toLocaleString()} sample{totalN === 1 ? '' : 's'} across {rows.length}{' '}
              pair{rows.length === 1 ? '' : 's'}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
