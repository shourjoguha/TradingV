/**
 * useUrlState — sync a single piece of state to a URL search-param.
 *
 * Architect issue #6: many pages store filter/sort state in `useState`
 * which gets reset on back-button. This helper makes URL adoption
 * trivial:
 *
 *   const [tab, setTab] = useUrlState('tab', 'open')
 *
 * Behaviour:
 *   - reads from URL on first render
 *   - writes via `setSearchParams({ replace: true })` so back-button
 *     navigates to the prior page, not prior filter state
 *   - falls back to default when param missing or invalid
 *   - generic over string types; for numbers/booleans the caller can wrap
 *
 * Not adopted everywhere yet — opt-in per page.
 */
import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

export function useUrlState<T extends string>(
  key: string,
  defaultValue: T,
): [T, (next: T) => void] {
  const [search, setSearch] = useSearchParams()
  const raw = search.get(key)
  const value = (raw as T | null) ?? defaultValue
  const setValue = useCallback(
    (next: T) => {
      const params = new URLSearchParams(search)
      if (next === defaultValue) {
        params.delete(key)
      } else {
        params.set(key, next)
      }
      setSearch(params, { replace: true })
    },
    [key, search, setSearch, defaultValue],
  )
  return [value, setValue]
}
