import { Link } from 'react-router-dom'
import { TrendingUp, ArrowRight } from 'lucide-react'
import { useMacroSeries } from '../../hooks/use-api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'

function weekAgoIso(): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - 7)
  return d.toISOString().split('T')[0]
}

/**
 * Today landing card: market mood preview.
 *
 * Two headline series — VIX (volatility) and SPY (broad-market 1w move) —
 * computed from the macro signal layer. Click-through to /macro for the
 * full regime workbench.
 */
export function MarketMoodCard() {
  const since = weekAgoIso()
  const vix = useMacroSeries({ symbol: '^VIX', since })
  const spy = useMacroSeries({ symbol: 'SPY', since })

  const vixPoints = vix.data?.points ?? []
  const spyPoints = spy.data?.points ?? []
  const vixLast = vixPoints[vixPoints.length - 1]?.value
  const spyFirst = spyPoints[0]?.value
  const spyLast = spyPoints[spyPoints.length - 1]?.value
  const spyDeltaPct = spyFirst && spyLast ? ((spyLast - spyFirst) / spyFirst) * 100 : null

  const vixLabel =
    vixLast == null
      ? '—'
      : vixLast > 25
        ? 'elevated'
        : vixLast > 18
          ? 'firm'
          : vixLast > 14
            ? 'neutral'
            : 'calm'

  const spyColor =
    spyDeltaPct == null
      ? 'text-muted-foreground'
      : spyDeltaPct > 0
        ? 'text-success'
        : spyDeltaPct < 0
          ? 'text-danger'
          : 'text-muted-foreground'

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <TrendingUp className="h-4 w-4 text-violet" />
          Market mood
        </CardTitle>
        <CardDescription className="text-xs">
          Macro context: volatility regime + broad-market 1w move. Drift
          alerts and rule firings re-rank around this backdrop.
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-1.5">
          <div className="flex items-baseline gap-3 text-sm">
            <div>
              <span className="text-xs text-muted-foreground">VIX </span>
              <span className="font-mono font-semibold">
                {vixLast == null ? '—' : vixLast.toFixed(1)}
              </span>
              <span className="text-xs text-muted-foreground"> · {vixLabel}</span>
            </div>
          </div>
          <div className="flex items-baseline gap-2 text-sm">
            <span className="text-xs text-muted-foreground">SPY 1w</span>
            <span className={`font-mono font-semibold ${spyColor}`}>
              {spyDeltaPct == null
                ? '—'
                : `${spyDeltaPct > 0 ? '+' : ''}${spyDeltaPct.toFixed(2)}%`}
            </span>
          </div>
          <Link
            to="/macro"
            className="inline-flex items-center gap-1 text-xs text-violet hover:text-violet/80"
          >
            Open macro <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      </CardContent>
    </Card>
  )
}
