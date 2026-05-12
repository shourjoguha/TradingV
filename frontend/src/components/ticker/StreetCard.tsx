import { Link } from 'react-router-dom'
import { Building2, ArrowRight } from 'lucide-react'
import { useStreetTicker } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'

interface Props {
  symbol: string
}

/**
 * Per-symbol smart-money strip on the Ticker Hub.
 *
 * Surfaces every snapshot row that mentions this ticker — date, channel
 * counts, total signals, ETF flag, notable string. Empty state suggests
 * The Street universe view. Lives next to predictions/TV-context so the
 * operator sees institutional positioning while sizing a name.
 */
export function StreetCard({ symbol }: Props) {
  const { data, isLoading } = useStreetTicker(symbol)
  const rows = data?.items ?? []

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Building2 className="h-4 w-4 text-violet" />
          The Street
        </CardTitle>
        <Link
          to="/the-street"
          className="text-xs text-muted-foreground hover:text-violet flex items-center gap-1"
        >
          Universe <ArrowRight className="h-3 w-3" />
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-xs text-muted-foreground italic">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No snapshot mentions {symbol} yet.
          </div>
        ) : (
          <div className="space-y-1.5">
            {rows.map((r) => (
              <div
                key={r.date}
                className="flex items-center justify-between gap-2 rounded-2xl shadow-inset-sm bg-background px-3 py-2 min-w-0"
              >
                <div className="flex items-baseline gap-2 min-w-0 flex-1">
                  <Badge variant="outline" className="text-[10px] shrink-0">
                    {r.date}
                  </Badge>
                  <span className="text-xs font-mono whitespace-nowrap">
                    {r.channels} ch · {r.total_signals} sig
                  </span>
                  {r.etf && (
                    <Badge variant="secondary" className="text-[10px] shrink-0">
                      ETF
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-1.5 text-[10px] font-mono shrink-0">
                  {r.billionaires > 0 && (
                    <span title="Billionaires">B{r.billionaires}</span>
                  )}
                  {r.trailblazers > 0 && (
                    <span title="Trailblazers">T{r.trailblazers}</span>
                  )}
                  {r.insiders > 0 && (
                    <span title="Insiders">I{r.insiders}</span>
                  )}
                  {r.politicians > 0 && (
                    <span title="Politicians">P{r.politicians}</span>
                  )}
                  {r.options_bullish > 0 && (
                    <span title="Options-Bullish">O{r.options_bullish}</span>
                  )}
                </div>
              </div>
            ))}
            {rows[0]?.notable && (
              <div className="text-xs text-muted-foreground italic line-clamp-2 pt-1">
                {rows[0].notable}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
