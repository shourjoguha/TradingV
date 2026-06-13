import { Link } from 'react-router-dom'
import { LineChart as LineChartIcon, ArrowRight } from 'lucide-react'
import { useAccuracyPair } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'

interface Props {
  symbol: string
}

/**
 * Predictions section of the Ticker Hub.
 *
 * Shows the most recent accuracy-pair rows (h+1 by default) so the
 * operator can see how the model has been doing on this name without
 * leaving the hub. Full grid + by-target chart at /predictions.
 */
export function PredictionStrip({ symbol }: Props) {
  const { data, isLoading } = useAccuracyPair({
    ticker: symbol,
    horizon_offset: 1,
    limit: 5,
  })

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <LineChartIcon className="h-4 w-4 text-primary" />
          Recent predictions (h+1)
        </CardTitle>
        <Link
          to={`/predictions/target?ticker=${symbol}`}
          className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1"
        >
          By target <ArrowRight className="h-3 w-3" />
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-xs text-muted-foreground italic">Loading…</div>
        ) : !data || data.rows.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No accuracy rows yet for {symbol} at h+1. Run an analysis to seed.
          </div>
        ) : (
          <div className="space-y-2">
            {data.rows.slice(0, 5).map((r) => (
              <div
                key={r.prediction_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-2xl shadow-inset-sm bg-background px-3 py-2 text-xs"
              >
                <span className="font-mono whitespace-nowrap">
                  {r.made_on} → {r.target_date}
                </span>
                <span className="font-mono whitespace-nowrap min-w-0 truncate">
                  pred ${r.predicted_close.toFixed(2)} · actual{' '}
                  ${r.actual_close.toFixed(2)}
                </span>
                <Badge
                  variant="outline"
                  className={`text-xs ${
                    Math.abs(r.error_pct) < 0.02
                      ? 'bg-success-bg text-success-fg'
                      : Math.abs(r.error_pct) < 0.05
                        ? ''
                        : 'bg-danger-bg text-danger-fg'
                  }`}
                >
                  {r.error_pct >= 0 ? '+' : ''}
                  {(r.error_pct * 100).toFixed(2)}%
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
