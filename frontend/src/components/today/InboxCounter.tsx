/**
 * InboxCounter — single counter row for three pending queues.
 *
 * Replaces the three vertically-stacked-strip pattern (TickerReviewStrip
 * + TVContextStrip + PendingReviewPanel) on Today's primary view. Each
 * sub-counter is a chip-style link; full strips are still reachable via
 * the dedicated tabs and are rendered below in their original form for
 * operators who want the inline expand. This row gives at-a-glance
 * inbox-zero affordance: when all three are 0, the whole strip hides.
 *
 * Phase 3 — Today reshape, addresses UX strategist O7 (three inboxes
 * for one workflow) without removing functionality the operator may
 * have built muscle memory around.
 */
import { Link } from 'react-router-dom'
import { Camera, Eye, Inbox, Search } from 'lucide-react'
import { useTickerReviewQueue, useResearchQueries, useTVContextRecent } from '../../hooks/use-api'
import { Card, CardContent } from '../ui/card'
import { Badge } from '../ui/badge'

interface CounterProps {
  icon: React.ComponentType<{ className?: string }>
  label: string
  count: number
  to: string
}

function Counter({ icon: Icon, label, count, to }: CounterProps) {
  const muted = count === 0
  return (
    <Link
      to={to}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-full transition-all ${
        muted
          ? 'text-muted-foreground hover:text-foreground'
          : 'text-foreground hover:shadow-extruded-sm'
      }`}
    >
      <Icon className="h-4 w-4" />
      <span className="text-sm">{label}</span>
      <Badge
        variant="outline"
        className={`tabular-nums text-[10px] ${
          muted ? 'text-muted-foreground' : 'text-violet border-violet/40'
        }`}
      >
        {count}
      </Badge>
    </Link>
  )
}

export function InboxCounter() {
  const tickerQueue = useTickerReviewQueue({ status: 'pending', limit: 50 })
  const research = useResearchQueries({
    status: 'pending',
    order: 'score',
    includeDeferred: false,
    limit: 50,
  })
  // TV-context: list-all hook (2026-05-17), no per-ticker fan-out needed.
  const tvCtx = useTVContextRecent({ limit: 50 })

  const tickerCount = tickerQueue.data?.items?.length ?? 0
  const researchCount = research.data?.items?.length ?? 0
  const tvCount = tvCtx.data?.length ?? 0
  const total = tickerCount + researchCount + tvCount

  // Hide the row entirely when everything is zero — operator-respectful empty state.
  if (total === 0) return null

  return (
    <Card>
      <CardContent className="py-3 px-4 flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mr-2">
          <Inbox className="h-4 w-4" />
          <span>Inbox</span>
          <Badge
            variant="outline"
            className="tabular-nums text-[10px] text-violet border-violet/40"
          >
            {total}
          </Badge>
        </div>
        <div className="flex items-center gap-1 ml-auto">
          <Counter icon={Search} label="Tickers to review" count={tickerCount} to="/" />
          <Counter icon={Camera} label="TV context" count={tvCount} to="/tv-context" />
          <Counter icon={Eye} label="Research approvals" count={researchCount} to="/research" />
        </div>
      </CardContent>
    </Card>
  )
}
