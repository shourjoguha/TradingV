import { Link } from 'react-router-dom'
import { FlaskConical } from 'lucide-react'
import { useHypotheses } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'

interface Props {
  symbol: string
}

/**
 * Hypothesis section for the Ticker Hub.
 *
 * Phase 2 implementation: client-side filter against the global active
 * hypothesis list. Matches when symbol appears in the slug, axis, or in
 * any invalidator's `args.symbol` (best-effort; the global list does not
 * carry full body text). Phase 3 will replace with a server-side filter
 * once `Hypothesis.tickers` becomes a first-class column.
 */
export function HypothesisRow({ symbol }: Props) {
  const { data, isLoading } = useHypotheses({ status: 'active' })
  const upper = symbol.toUpperCase()
  const all = data?.items ?? []
  const matches = all.filter((h) => {
    const blob = `${h.slug ?? ''} ${h.axis ?? ''}`.toUpperCase()
    if (blob.includes(upper)) return true
    const inv = h.invalidator as any
    if (inv?.args?.symbol && String(inv.args.symbol).toUpperCase() === upper)
      return true
    return false
  })

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-primary" />
          Theses on {symbol}
        </CardTitle>
        <Link to="/theses" className="text-xs text-muted-foreground hover:text-primary">
          All theses
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-xs text-muted-foreground italic">Loading…</div>
        ) : matches.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No active hypothesis touches {symbol}.
          </div>
        ) : (
          <div className="space-y-2">
            {matches.map((h) => (
              <Link
                key={h.id}
                to={`/theses?id=${h.id}`}
                className="block rounded-2xl shadow-inset-sm bg-background p-3 hover:shadow-extruded-sm transition-all"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium truncate">{h.slug}</div>
                  <Badge variant="outline" className="text-xs shrink-0">
                    {h.status}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground line-clamp-2 mt-1">
                  {h.axis} · {h.claim_type}
                </div>
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
