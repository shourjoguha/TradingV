import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Play, ChevronDown, ChevronRight } from 'lucide-react'
import { useFireNow, useSchedule } from '../hooks/use-api'
import { Button } from '../components/ui/button'
import { DriftBanner } from '../components/today/DriftBanner'
import { ResearchApprovalStrip } from '../components/today/ResearchApprovalStrip'
import { FreshSignalsStrip } from '../components/today/FreshSignalsStrip'
import { TVContextStrip } from '../components/today/TVContextStrip'
import { WatchlistDelta } from '../components/today/WatchlistDelta'
import { RegimeStrip } from '../components/dashboard/RegimeStrip'

const COLLAPSE_KEY = 'today.section.collapsed'

interface CollapseState {
  regime?: boolean
}

function readCollapse(): CollapseState {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(COLLAPSE_KEY)
    return raw ? (JSON.parse(raw) as CollapseState) : {}
  } catch {
    return {}
  }
}

function writeCollapse(state: CollapseState): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(COLLAPSE_KEY, JSON.stringify(state))
}

/**
 * Today — single-screen morning catch-up.
 *
 * Replaces the legacy generic Dashboard at the root route. Surfaces the
 * morning-priority bundle: drift alerts → pending research approvals →
 * fresh opportunities since the last visit. Lower-priority context
 * (regime context, schedule, queue, recent jobs) lives at /admin/overview
 * via the legacy Dashboard, which stays around as a quarterly admin page.
 *
 * Phase 1 wires Drift / Research / Fresh Signals only. Phase 2 will add
 * TV Context strip + Watchlist Delta.
 */
export function Today() {
  const { data: schedule } = useSchedule()
  const { mutate: fireNow, isPending: isFiring } = useFireNow()
  const [collapse, setCollapse] = useState<CollapseState>(() => readCollapse())

  useEffect(() => {
    writeCollapse(collapse)
  }, [collapse])

  const toggleRegime = () =>
    setCollapse((c) => ({ ...c, regime: !c.regime }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">
            Today
          </h2>
          <p className="text-muted-foreground text-sm">
            Morning catch-up: drift, pending research, fresh signals.
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

      <DriftBanner />

      <ResearchApprovalStrip />

      <FreshSignalsStrip />

      <TVContextStrip />

      <WatchlistDelta />

      {/* Collapsed-by-default regime context — operator can expand if needed. */}
      <div className="space-y-2">
        <button
          type="button"
          onClick={toggleRegime}
          aria-expanded={!collapse.regime}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-2xl text-sm font-medium text-muted-foreground hover:text-foreground hover:shadow-extruded-sm transition-all"
        >
          {collapse.regime ? (
            <ChevronRight className="h-3.5 w-3.5 opacity-60" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 opacity-60" />
          )}
          Regime context
        </button>
        {!collapse.regime && <RegimeStrip />}
      </div>

      <div className="text-xs text-muted-foreground italic pt-4">
        Looking for the old dashboard?{' '}
        <Link to="/admin/overview" className="text-violet hover:underline">
          Open it here
        </Link>
        .
      </div>
    </div>
  )
}
