import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { List, ArrowRight } from 'lucide-react'
import { useWatchlist } from '../../hooks/use-api'
import { TickerLink } from '../common/TickerLink'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'

const SNAPSHOT_KEY = 'today.watchlist.snapshot'

interface RosterSnapshot {
  symbols: string[]
  capturedAt: number
}

function readSnapshot(): RosterSnapshot | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(SNAPSHOT_KEY)
    return raw ? (JSON.parse(raw) as RosterSnapshot) : null
  } catch {
    return null
  }
}

function writeSnapshot(snap: RosterSnapshot): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snap))
}

/**
 * Watchlist delta — diff the current roster against the operator's last
 * visit's snapshot. Highlights additions/removals as a one-line summary
 * + chip lists. Snapshot updates on unmount.
 *
 * Pure client-side; no backend cost.
 */
export function WatchlistDelta() {
  const { data, isLoading } = useWatchlist({ limit: 1000 })
  const symbols = (data?.entries ?? [])
    .map((e: any) => (e.symbol ?? e.ticker) as string)
    .filter(Boolean)

  const [prev] = useState<RosterSnapshot | null>(() => readSnapshot())

  useEffect(() => {
    if (symbols.length === 0) return
    return () => {
      writeSnapshot({ symbols, capturedAt: Date.now() })
    }
  }, [symbols])

  if (isLoading) return null

  const current = new Set(symbols)
  const previous = new Set(prev?.symbols ?? [])
  const added = symbols.filter((s) => !previous.has(s))
  const removed = (prev?.symbols ?? []).filter((s) => !current.has(s))

  if (!prev || (added.length === 0 && removed.length === 0)) {
    return null
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <List className="h-4 w-4 text-primary" />
          Watchlist delta
        </CardTitle>
        <Link
          to="/roster"
          className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1"
        >
          Roster <ArrowRight className="h-3 w-3" />
        </Link>
      </CardHeader>
      <CardContent className="space-y-2">
        {added.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="bg-success-bg text-success-fg">
              +{added.length} added
            </Badge>
            {added.slice(0, 12).map((s) => (
              <TickerLink key={s} symbol={s} chip />
            ))}
            {added.length > 12 && (
              <span className="text-xs text-muted-foreground">
                +{added.length - 12} more
              </span>
            )}
          </div>
        )}
        {removed.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="bg-danger-bg text-danger-fg">
              -{removed.length} removed
            </Badge>
            {removed.slice(0, 12).map((s) => (
              <span
                key={s}
                className="px-2 py-0.5 rounded-full shadow-inset-sm font-mono text-xs text-muted-foreground line-through"
              >
                {s}
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
