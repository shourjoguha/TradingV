import { useParams, Link } from 'react-router-dom'
import { useTVContextByTicker, useOpportunities, useTrades } from '../hooks/use-api'
import { HeaderStrip } from '../components/ticker/HeaderStrip'
import { PredictionStrip } from '../components/ticker/PredictionStrip'
import { StreetCard } from '../components/ticker/StreetCard'
import { VaultChunkList } from '../components/ticker/VaultChunkList'
import { HypothesisRow } from '../components/ticker/HypothesisRow'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Badge } from '../components/ui/badge'
import { Camera, Target, Receipt } from 'lucide-react'

/**
 * Ticker Hub — `/ticker/:symbol`
 *
 * Single scroll-anchored screen that aggregates every per-symbol surface
 * the operator might want when reasoning about a name: predictions,
 * recent TV Context, hypotheses touching the symbol, smart-money mentions,
 * vault chunks (semantic search), open opportunities, recent trades.
 *
 * Phase 2 of the IA reorg. Replaces the multi-page hop pattern.
 */
export function TickerHub() {
  const params = useParams<{ symbol: string }>()
  const symbol = (params.symbol ?? '').toUpperCase()

  if (!symbol) {
    return (
      <div className="text-sm text-muted-foreground italic">
        No ticker in route. Open <code>/ticker/SYM</code>.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <HeaderStrip symbol={symbol} />

      <div className="grid gap-4 lg:grid-cols-2">
        <PredictionStrip symbol={symbol} />
        <StreetCard symbol={symbol} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <TVContextSection symbol={symbol} />
        <HypothesisRow symbol={symbol} />
      </div>

      <VaultChunkList symbol={symbol} />

      <div className="grid gap-4 lg:grid-cols-2">
        <OpportunitiesSection symbol={symbol} />
        <TradesSection symbol={symbol} />
      </div>
    </div>
  )
}

function TVContextSection({ symbol }: { symbol: string }) {
  const { data, isLoading } = useTVContextByTicker(symbol)
  const items = data ?? []
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Camera className="h-4 w-4 text-violet" />
          Recent TV Context
        </CardTitle>
        <Link
          to={`/tv-context/${symbol}`}
          className="text-xs text-muted-foreground hover:text-violet"
        >
          Inbox
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-xs text-muted-foreground italic">Loading…</div>
        ) : items.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No context items for {symbol}. Drop a screenshot or note via the inbox.
          </div>
        ) : (
          <div className="space-y-1.5">
            {items.slice(0, 5).map((it) => (
              <div
                key={it.id}
                className="flex items-center justify-between gap-2 rounded-2xl shadow-inset-sm bg-background px-3 py-2 text-xs"
              >
                <Badge variant="outline" className="text-[10px] shrink-0">
                  {it.kind}
                </Badge>
                <span className="font-mono text-muted-foreground truncate">
                  {new Date(it.captured_at).toLocaleDateString()}
                </span>
                <span className="text-[10px] text-muted-foreground truncate flex-1">
                  {it.source}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function OpportunitiesSection({ symbol }: { symbol: string }) {
  // Server-side ticker filter — avoids re-pulling the full open-opps list
  // every time a Hub renders.
  const { data, isLoading } = useOpportunities({
    status: 'open',
    ticker: symbol,
    limit: 20,
  })
  const matches = data?.items ?? []
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Target className="h-4 w-4 text-violet" />
          Open opportunities
        </CardTitle>
        <Link
          to="/motion/opportunities"
          className="text-xs text-muted-foreground hover:text-violet"
        >
          All
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-xs text-muted-foreground italic">Loading…</div>
        ) : matches.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No open opps on {symbol}.
          </div>
        ) : (
          <div className="space-y-1.5">
            {matches.map((o) => (
              <Link
                key={o.id}
                to="/motion/opportunities"
                className="block rounded-2xl shadow-inset-sm bg-background p-3 hover:shadow-extruded-sm transition-all"
              >
                <div className="flex items-center justify-between gap-2 text-xs">
                  <Badge
                    variant="outline"
                    className={
                      o.kind === 'buy'
                        ? 'bg-success-bg text-success-fg'
                        : 'bg-danger-bg text-danger-fg'
                    }
                  >
                    {o.kind.toUpperCase()}
                  </Badge>
                  <span
                    className={`font-mono tabular-nums ${
                      o.predicted_move_pct >= 0 ? 'text-success' : 'text-danger'
                    }`}
                  >
                    {o.predicted_move_pct >= 0 ? '+' : ''}
                    {(o.predicted_move_pct * 100).toFixed(2)}%
                  </span>
                  <span className="font-mono">
                    conf {(o.confidence * 100).toFixed(0)}%
                  </span>
                  <span className="text-muted-foreground truncate">
                    {o.rule_label || o.rule_id}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function TradesSection({ symbol }: { symbol: string }) {
  // Server-side ticker filter — keep the journal pull tight.
  const { data, isLoading } = useTrades({ ticker: symbol, limit: 10 })
  const matches = data?.items ?? []
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Receipt className="h-4 w-4 text-violet" />
          Recent trades
        </CardTitle>
        <Link
          to="/motion/trades"
          className="text-xs text-muted-foreground hover:text-violet"
        >
          Journal
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-xs text-muted-foreground italic">Loading…</div>
        ) : matches.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No trades on {symbol}.
          </div>
        ) : (
          <div className="space-y-1.5">
            {matches.slice(0, 5).map((t: any) => (
              <div
                key={t.id}
                className="rounded-2xl shadow-inset-sm bg-background p-3 text-xs"
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge
                    variant="outline"
                    className={
                      t.side === 'long'
                        ? 'bg-success-bg text-success-fg'
                        : 'bg-danger-bg text-danger-fg'
                    }
                  >
                    {String(t.side ?? '').toUpperCase()}
                  </Badge>
                  <span className="font-mono text-muted-foreground">
                    {t.entry_at
                      ? new Date(t.entry_at).toLocaleDateString()
                      : '—'}
                  </span>
                  {t.pnl_pct != null && (
                    <span
                      className={`font-mono tabular-nums ${
                        t.pnl_pct >= 0 ? 'text-success' : 'text-danger'
                      }`}
                    >
                      {t.pnl_pct >= 0 ? '+' : ''}
                      {(t.pnl_pct * 100).toFixed(2)}%
                    </span>
                  )}
                  <span className="text-muted-foreground truncate">
                    {t.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
