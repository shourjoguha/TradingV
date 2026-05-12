import { Link } from 'react-router-dom'
import { Camera, ArrowRight } from 'lucide-react'
import { useWatchlist, useTVContextByTicker } from '../../hooks/use-api'
import { TickerLink } from '../common/TickerLink'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import type { TVContextItem } from '../../lib/types'

const LAST_VISIT_KEY = 'today.last_visited_at'

function readLastVisit(): number {
  if (typeof window === 'undefined') return 0
  const raw = window.localStorage.getItem(LAST_VISIT_KEY)
  const n = raw ? Number(raw) : 0
  return Number.isFinite(n) ? n : 0
}

/**
 * Today's TV Context strip — shows recent context items across the
 * roster's top tickers (limit 8). Items captured since the operator's
 * last visit are flagged. Clicking any row deep-links into the per-ticker
 * inbox.
 *
 * Phase 2 — pragmatic implementation: queries the per-ticker endpoint
 * for each of the top-K roster tickers and merges client-side. A future
 * `/v1/tv-context/recent?since=<ts>` endpoint would replace this.
 */
export function TVContextStrip({ limit = 8 }: { limit?: number }) {
  const watchlist = useWatchlist({ limit: 8 })
  const tickers: string[] = (watchlist.data?.entries ?? [])
    .map((e: any) => e.symbol ?? e.ticker)
    .filter(Boolean)
    .slice(0, 8)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Camera className="h-4 w-4 text-violet" />
          Recent TV Context
        </CardTitle>
        <Link
          to="/tv-context"
          className="text-xs text-muted-foreground hover:text-violet flex items-center gap-1"
        >
          Inbox <ArrowRight className="h-3 w-3" />
        </Link>
      </CardHeader>
      <CardContent>
        {tickers.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            Roster empty — add tickers to start collecting context.
          </div>
        ) : (
          <TickerStripBody tickers={tickers} limit={limit} />
        )}
      </CardContent>
    </Card>
  )
}

function TickerStripBody({
  tickers,
  limit,
}: {
  tickers: string[]
  limit: number
}) {
  const lastVisit = readLastVisit()
  // Eight identical hooks, one per ticker. React Query dedupes, so
  // re-render cost is modest. Hard-cap to 8 above so this is bounded.
  const q0 = useTVContextByTicker(tickers[0] ?? null)
  const q1 = useTVContextByTicker(tickers[1] ?? null)
  const q2 = useTVContextByTicker(tickers[2] ?? null)
  const q3 = useTVContextByTicker(tickers[3] ?? null)
  const q4 = useTVContextByTicker(tickers[4] ?? null)
  const q5 = useTVContextByTicker(tickers[5] ?? null)
  const q6 = useTVContextByTicker(tickers[6] ?? null)
  const q7 = useTVContextByTicker(tickers[7] ?? null)
  const all: TVContextItem[] = [q0, q1, q2, q3, q4, q5, q6, q7]
    .flatMap((q) => q.data ?? [])
    .filter((it) => it.status === 'active')

  const sorted = [...all].sort(
    (a, b) =>
      new Date(b.captured_at).getTime() - new Date(a.captured_at).getTime(),
  )
  const display = sorted.slice(0, limit)
  const freshCount = sorted.filter(
    (it) => new Date(it.captured_at).getTime() > lastVisit,
  ).length

  if (display.length === 0) {
    return (
      <div className="text-xs text-muted-foreground italic">
        No active context items across roster.
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      {freshCount > 0 && (
        <Badge variant="outline" className="text-[10px]">
          {freshCount} new since last visit
        </Badge>
      )}
      {display.map((it) => {
        const isFresh = new Date(it.captured_at).getTime() > lastVisit
        return (
          <div
            key={it.id}
            className={`flex items-center gap-2 rounded-2xl shadow-inset-sm bg-background px-3 py-2 text-xs min-w-0 ${
              isFresh ? 'ring-1 ring-violet/30' : ''
            }`}
          >
            <Badge variant="outline" className="text-[10px] shrink-0">
              {it.kind}
            </Badge>
            {it.ticker && (
              <span className="shrink-0">
                <TickerLink symbol={it.ticker} />
              </span>
            )}
            <span className="font-mono text-muted-foreground shrink-0">
              {new Date(it.captured_at).toLocaleDateString()}
            </span>
            <span className="text-muted-foreground truncate min-w-0 flex-1">
              {it.source}
            </span>
          </div>
        )
      })}
    </div>
  )
}
