import { Link } from 'react-router-dom'
import { Play } from 'lucide-react'
import { useFireNow, useSchedule } from '../hooks/use-api'
import { Button } from '../components/ui/button'
import { DriftCard } from '../components/today/DriftCard'
import { FreshSignalsCard } from '../components/today/FreshSignalsCard'
import { ResearchCuriousCard } from '../components/today/ResearchCuriousCard'
import { MarketMoodCard } from '../components/today/MarketMoodCard'
import { TVContextStrip } from '../components/today/TVContextStrip'
import { WatchlistDelta } from '../components/today/WatchlistDelta'
import { PendingReviewPanel } from '../components/today/PendingReviewPanel'

/**
 * Today — single-screen morning catch-up, demo-inspired 2×2 narrative grid.
 *
 * Layout:
 *  1. Page header + Run Now button
 *  2. 2×2 grid of narrative cards (drift, fresh signals, research curiosity,
 *     market mood). Each card has a role description that survives empty
 *     state. NO inline action buttons — clicks navigate to dedicated pages.
 *  3. Secondary rows: TV Context strip + Watchlist delta.
 *  4. PendingReviewPanel at the bottom — top-5 by composite score, inline
 *     expand for approve/dismiss. Backlog link to /research?status=pending.
 *
 * Operator pain solved (2026-05-13 brainstorm):
 *  - 10+ pending approvals stacked above the fold → cognitive overload
 *    → blanket dismissal. New layout: cap visible to 5, ranked by score
 *    not chronology, inline expand only when operator engages, auto-age
 *    after 30d via the retention loop (see app/research/ranking.py).
 */
export function Today() {
  const { data: schedule } = useSchedule()
  const { mutate: fireNow, isPending: isFiring } = useFireNow()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">
            Today
          </h2>
          <p className="text-muted-foreground text-sm">
            Morning glance: where the model is misfiring, what it might pursue,
            what it's curious about, and the market mood.
          </p>
        </div>
        <Button
          onClick={() => fireNow()}
          disabled={isFiring || !schedule?.enabled}
          size="lg"
        >
          <Play className="mr-2 h-4 w-4" />
          Run Now
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <DriftCard />
        <FreshSignalsCard />
        <ResearchCuriousCard />
        <MarketMoodCard />
      </div>

      <TVContextStrip />

      <WatchlistDelta />

      <PendingReviewPanel />

      <div className="text-xs text-muted-foreground italic pt-4">
        Looking for the legacy dashboard?{' '}
        <Link to="/admin/overview" className="text-violet hover:underline">
          Open it here
        </Link>
        .
      </div>
    </div>
  )
}
