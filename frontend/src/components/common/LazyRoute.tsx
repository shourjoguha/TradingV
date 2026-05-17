import { ComponentType, lazy, Suspense } from 'react'
import { Skeleton } from '../ui/skeleton'

/**
 * LazyRoute — drop the per-route Suspense+Skeleton boilerplate.
 *
 * Architect issue #8: App.tsx has 11 routes each wrapped in identical
 * `<Suspense fallback={<Skeleton className="h-40 w-full" />}><X /></Suspense>`.
 * This helper centralises the pattern.
 *
 * Usage:
 *   const RxFinance = lazy(() => import('./pages/RxFinance').then(m => ({ default: m.RxFinance })))
 *   <Route path="/motion/recs" element={<LazyRoute Component={RxFinance} />} />
 */
export function LazyRoute({
  Component,
  fallbackHeight = 'h-40',
}: {
  Component: ComponentType
  fallbackHeight?: 'h-40' | 'h-60'
}) {
  return (
    <Suspense fallback={<Skeleton className={`${fallbackHeight} w-full`} />}>
      <Component />
    </Suspense>
  )
}

/**
 * lazyPage — sugar for `lazy(() => import(...).then(m => ({ default: m.X })))`.
 * Returns a component ready to pass to `<LazyRoute Component={lazyPage(...)} />`.
 */
export function lazyPage<T extends ComponentType>(
  loader: () => Promise<Record<string, T>>,
  exportName: string,
): T {
  return lazy(() => loader().then((m) => ({ default: m[exportName] }))) as unknown as T
}
