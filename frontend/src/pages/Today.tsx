import { Play, Sun } from 'lucide-react'
import { useFireNow, useSchedule } from '../hooks/use-api'
import { Button } from '../components/ui/button'
import { DriftCard } from '../components/today/DriftCard'
import { FreshSignalsCard } from '../components/today/FreshSignalsCard'
import { ResearchCuriousCard } from '../components/today/ResearchCuriousCard'
import { MarketMoodCard } from '../components/today/MarketMoodCard'
import { TVContextStrip } from '../components/today/TVContextStrip'
import { WatchlistDelta } from '../components/today/WatchlistDelta'
import { PendingReviewPanel } from '../components/today/PendingReviewPanel'
import { TickerReviewStrip } from '../components/today/TickerReviewStrip'
import { RxStrip } from '../components/today/RxStrip'
import { InboxCounter } from '../components/today/InboxCounter'
import { PageHeader } from '../components/common/PageHeader'

/**
 * Today — morning catch-up.
 *
 * Phase 3 reshape (2026-05-17 UX rework):
 *   - Zone 1 — Action queue: RxStrip (open recs, hidden when empty)
 *   - Zone 2 — Inbox aggregate: InboxCounter (ticker review + research approvals)
 *   - Zone 3 — What changed: 4-up compact grid (drift / signals / research curious / market mood)
 *   - Zone 4 — Inbox detail (expand-on-engage): TickerReviewStrip, TVContextStrip, WatchlistDelta, PendingReviewPanel
 *
 * Preserves all existing functionality so muscle memory survives, but
 * gives the operator immediate inbox-zero affordance via the counter
 * row + RxStrip at top. Auto-collapses when nothing is pending.
 */
export function Today() {
  const { data: schedule } = useSchedule()
  const { mutate: fireNow, isPending: isFiring } = useFireNow()

  return (
    <div className="space-y-4">
      <PageHeader
        icon={Sun}
        title="Today"
        description="Morning glance: open decisions, what changed overnight, what's in the inbox."
        actions={
          <Button
            onClick={() => fireNow()}
            disabled={isFiring || !schedule?.enabled}
            size="lg"
          >
            <Play className="mr-2 h-4 w-4" />
            Run Now
          </Button>
        }
      />

      {/* Zone 1: Action queue — what needs me right now */}
      <RxStrip />

      {/* Zone 2: Inbox aggregate — single-line counter w/ click-through */}
      <InboxCounter />

      {/* Zone 3: What changed — compact 4-up grid */}
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        <DriftCard />
        <FreshSignalsCard />
        <ResearchCuriousCard />
        <MarketMoodCard />
      </div>

      {/* Zone 4: Inbox detail — strips with inline actions (operator who
          wants to triage without leaving Today gets the full surfaces) */}
      <TickerReviewStrip />

      <TVContextStrip />

      <WatchlistDelta />

      <PendingReviewPanel />
    </div>
  )
}
