import { Link } from 'react-router-dom'
import { Plus, Trash2, ExternalLink } from 'lucide-react'
import {
  useQuotes,
  useTickerLabels,
  useWatchlist,
  useAddTicker,
  useDeleteTicker,
} from '../../hooks/use-api'
import { Card, CardContent } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Skeleton } from '../ui/skeleton'

interface Props {
  symbol: string
}

/**
 * Ticker Hub header — symbol, sector/cap labels, latest quote, watchlist
 * toggle, deep-link to TradingView.com chart. Single row on desktop;
 * stacks on mobile.
 */
export function HeaderStrip({ symbol }: Props) {
  const { data: labels } = useTickerLabels(symbol)
  const quotes = useQuotes([symbol])
  const watchlist = useWatchlist({ limit: 1000 })
  const onWatchlist = watchlist.data?.entries?.some(
    (e: any) => (e.ticker ?? e.symbol) === symbol,
  ) ?? false
  const addTicker = useAddTicker()
  const removeTicker = useDeleteTicker()

  const quote = quotes.data?.items?.find((q) => q.symbol === symbol)
  const labelEntries = Object.entries(labels?.labels ?? {})

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex flex-wrap items-baseline gap-3 min-w-0">
          <h2 className="text-3xl font-mono font-bold tracking-tight shrink-0">{symbol}</h2>
          {labels === undefined ? (
            <Skeleton className="h-4 w-24" />
          ) : (
            labelEntries.slice(0, 5).map(([k, v]) => (
              <Badge
                key={k}
                variant="outline"
                className="text-xs max-w-full truncate"
              >
                {k}: {String(v)}
              </Badge>
            ))
          )}
          <div className="ml-auto flex items-center gap-3 flex-wrap min-w-0">
            {quote && (
              <span className="text-lg font-mono tabular-nums">
                ${quote.last_close?.toFixed(2) ?? '—'}
                {quote.pct_1w !== null && quote.pct_1w !== undefined && (
                  <span
                    className={`ml-2 text-xs ${
                      quote.pct_1w >= 0 ? 'text-success' : 'text-danger'
                    }`}
                  >
                    {quote.pct_1w >= 0 ? '+' : ''}
                    {(quote.pct_1w * 100).toFixed(2)}% 1w
                  </span>
                )}
              </span>
            )}
            {onWatchlist ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => removeTicker.mutate(symbol)}
                disabled={removeTicker.isPending}
              >
                <Trash2 className="h-3 w-3 mr-1" />
                Roster
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => addTicker.mutate({ symbol })}
                disabled={addTicker.isPending}
              >
                <Plus className="h-3 w-3 mr-1" />
                Roster
              </Button>
            )}
            <Link
              to={`https://www.tradingview.com/symbols/${symbol}/`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1"
            >
              TV.com <ExternalLink className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
