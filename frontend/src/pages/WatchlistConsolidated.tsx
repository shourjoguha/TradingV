import { lazy, Suspense } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ListChecks } from 'lucide-react'
import { Watchlist } from './Watchlist'
import { Skeleton } from '../components/ui/skeleton'
import { InfoBubble } from '../components/common'

// Lazy-load Watchlists (boards UI) so the boards bundle only ships when
// the operator opens that tab.
const Watchlists = lazy(() =>
  import('./Watchlists').then((m) => ({ default: m.Watchlists })),
)

type Tab = 'boards' | 'roster'
// Boards first — the casual-tracking surface gets opened more often than
// the operational roster (which mostly drives Kronos in the background).
const TABS: { id: Tab; label: string }[] = [
  { id: 'boards', label: 'Boards' },
  { id: 'roster', label: 'Roster' },
]

/**
 * Consolidated Watchlist — `/watchlist/:tab?`
 *
 * Layout mirrors `/macro` and `/predictions`:
 *   row 1: title + description (left)
 *   row 2: segmented tabs (left, standalone — NOT inside the header row)
 *   row 3: tab content
 *
 * Two tabs: Roster (operational watchlist driving Kronos run; backed by
 * `/v1/watchlist`) and Boards (casual ticker lists with quotes; backed
 * by `/v1/boards`). Both backends remain separate; only the frontend
 * mental model collapses into one surface.
 */
export function WatchlistConsolidated() {
  const { tab: tabParam } = useParams<{ tab?: string }>()
  const navigate = useNavigate()
  const tab: Tab = (TABS.find((t) => t.id === tabParam)?.id ?? 'boards') as Tab

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
          <ListChecks className="h-5 w-5 text-muted-foreground" />
          Watchlist
          <InfoBubble term="watchlist_concept" />
        </h2>
        <p className="text-muted-foreground text-sm">
          Roster drives Kronos predictions; Boards are casual ticker lists. Same
          backend split as before — single surface for everyday use.
        </p>
      </div>

      <div
        role="tablist"
        aria-label="Watchlist view"
        className="inline-flex rounded-xl bg-background shadow-inset-sm p-1 gap-1"
      >
        {TABS.map((t) => {
          const active = t.id === tab
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={active}
              onClick={() =>
                navigate(t.id === 'boards' ? '/watchlist' : `/watchlist/${t.id}`)
              }
              className={[
                'px-3 py-1.5 rounded-lg text-xs transition-all',
                active
                  ? 'bg-card text-foreground shadow-extruded-sm font-medium'
                  : 'text-muted-foreground hover:text-foreground',
              ].join(' ')}
            >
              {t.label}
            </button>
          )
        })}
      </div>

      {tab === 'roster' && <Watchlist />}
      {tab === 'boards' && (
        <Suspense fallback={<Skeleton className="h-40 w-full" />}>
          <Watchlists />
        </Suspense>
      )}
    </div>
  )
}
