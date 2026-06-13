/**
 * useResolvedSeries — resolve an array of `SeriesSpec`s through the
 * existing TanStack-cached macro hooks in parallel. Uses `useQueries`
 * so each new series shares the same 5-min stale time and dedup as the
 * rest of the app.
 *
 * Cache-aware: same `(numerator, denominator, since)` key used by
 * `useMacroRatio` elsewhere in the app, so the builder is a free read
 * after first fetch.
 */
import { useQueries } from '@tanstack/react-query'
import { useBackend } from '../../../hooks/use-backend'
import { apiFetch } from '../../../lib/api'
import type { MacroRatioResponse, MacroSeriesResponse } from '../../../lib/types'
import type { ResolvedSeries, SeriesSpec } from './types'

function defaultLabel(spec: SeriesSpec): string {
  if (spec.kind === 'ratio') return spec.label ?? `${spec.numerator}/${spec.denominator}`
  return spec.label ?? spec.symbol
}

export function useResolvedSeries(
  specs: SeriesSpec[],
  since?: string,
): ResolvedSeries[] {
  const { backendId } = useBackend()
  const results = useQueries({
    queries: specs.map((spec) => {
      if (spec.kind === 'ratio') {
        return {
          queryKey: ['macro-ratio', backendId, spec.numerator, spec.denominator, since],
          queryFn: () => {
            const s = new URLSearchParams()
            s.set('numerator', spec.numerator)
            s.set('denominator', spec.denominator)
            if (since) s.set('since', since)
            return apiFetch<MacroRatioResponse>(`/v1/macro/ratio?${s}`, { backendId })
          },
          staleTime: 5 * 60_000,
        }
      }
      // series
      return {
        queryKey: ['macro-series', backendId, spec.symbol, since],
        queryFn: () => {
          const s = new URLSearchParams()
          s.set('symbol', spec.symbol)
          if (since) s.set('since', since)
          return apiFetch<MacroSeriesResponse>(`/v1/macro/series?${s}`, { backendId })
        },
        staleTime: 5 * 60_000,
      }
    }),
  })

  return specs.map((spec, i) => {
    const r = results[i]
    return {
      spec,
      label: defaultLabel(spec),
      points: r.data?.points ?? [],
      isLoading: r.isLoading,
      isError: r.isError,
    }
  })
}
