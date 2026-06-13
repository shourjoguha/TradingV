import { lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'
import { Opportunities } from './Opportunities'
import { Trades } from './Trades'
import { Skeleton } from '../components/ui/skeleton'
import { TabbedShell } from '../components/common/TabbedShell'

// Lazy-load the rx-layer surfaces so react-markdown + the rec pages only
// ship when the operator opens them.
const RxFinance = lazy(() =>
  import('./RxFinance').then((m) => ({ default: m.RxFinance })),
)
const RxFinanceDetail = lazy(() =>
  import('./RxFinanceDetail').then((m) => ({ default: m.RxFinanceDetail })),
)
const RxFinancePositions = lazy(() =>
  import('./RxFinancePositions').then((m) => ({ default: m.RxFinancePositions })),
)

const SuspendedRxFinance = () => (
  <Suspense fallback={<Skeleton className="h-40 w-full" />}>
    <RxFinance />
  </Suspense>
)
const SuspendedRxPositions = () => (
  <Suspense fallback={<Skeleton className="h-40 w-full" />}>
    <RxFinancePositions />
  </Suspense>
)
const SuspendedRxDetail = () => (
  <Suspense fallback={<Skeleton className="h-60 w-full" />}>
    <RxFinanceDetail />
  </Suspense>
)

/**
 * Motion — decide/act/hold/reflect shell.
 *
 *   /motion              → Opportunities (default)
 *   /motion/trades       → Trade journal
 *   /motion/positions    → Position aggregation
 *   /motion/recs         → rx recommendations list
 *   /motion/recs/:id     → rec detail (shell short-circuits)
 *
 * The `id` URL param indicates detail mode (literal `recs` segment means
 * `tab` is unbound). Phase 1 refactor — uses `TabbedShell` primitive.
 */
export function Motion() {
  const { id } = useParams<{ id?: string }>()

  return (
    <TabbedShell
      basePath="/motion"
      ariaLabel="Motion view"
      isDetail={!!id}
      detail={<SuspendedRxDetail />}
      tabs={[
        { id: 'opportunities', label: 'Opportunities', render: () => <Opportunities /> },
        { id: 'trades',        label: 'Trades',        render: () => <Trades /> },
        { id: 'positions',     label: 'Positions',     render: () => <SuspendedRxPositions /> },
        { id: 'recs',          label: 'Recommendations', render: () => <SuspendedRxFinance /> },
      ]}
    />
  )
}

export default Motion
