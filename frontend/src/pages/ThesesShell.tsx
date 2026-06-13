import { lazy, Suspense } from 'react'
import { Theses } from './Theses'
import { Skeleton } from '../components/ui/skeleton'
import { TabbedShell } from '../components/common/TabbedShell'

// Lazy-load the health view — only ships when operator opens it.
const RxFinanceHypotheses = lazy(() =>
  import('./RxFinanceHypotheses').then((m) => ({ default: m.RxFinanceHypotheses })),
)

const SuspendedHealth = () => (
  <Suspense fallback={<Skeleton className="h-40 w-full" />}>
    <RxFinanceHypotheses />
  </Suspense>
)

/**
 * Theses tab shell: List (default) + Health.
 * Phase 1 refactor — uses `TabbedShell` primitive.
 */
export function ThesesShell() {
  return (
    <TabbedShell
      basePath="/theses"
      ariaLabel="Theses view"
      tabs={[
        { id: 'list',   label: 'Theses', render: () => <Theses /> },
        { id: 'health', label: 'Health', render: () => <SuspendedHealth /> },
      ]}
    />
  )
}

export default ThesesShell
