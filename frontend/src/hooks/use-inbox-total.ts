/**
 * useInboxTotal — single source of truth for "how many things await
 * operator action across all inboxes". Sums three queues:
 *   - ticker_review_queue (status=pending)
 *   - research_queries    (status=pending, score-ordered, no deferred)
 *   - tv_context_items    (active, last 50)
 *
 * Used by:
 *   - `components/today/InboxCounter.tsx` (row total + per-queue chips)
 *   - `components/Layout.tsx` (K-logo ambient breathing ring when > 0,
 *     per Phase 6 color taxonomy — one-signal-app-wide rule)
 *
 * TanStack Query dedupes by cache key so calling the underlying hooks in
 * both consumers is free (no extra requests). Keeping totals derived
 * inline rather than in a Context avoids re-rendering the whole tree on
 * each refetch.
 */
import {
  useResearchQueries,
  useTickerReviewQueue,
  useTVContextRecent,
} from './use-api'

export function useInboxTotal(): number {
  const tickerQueue = useTickerReviewQueue({ status: 'pending', limit: 50 })
  const research = useResearchQueries({
    status: 'pending',
    order: 'score',
    includeDeferred: false,
    limit: 50,
  })
  const tvCtx = useTVContextRecent({ limit: 50 })

  const tickerCount = tickerQueue.data?.items?.length ?? 0
  const researchCount = research.data?.items?.length ?? 0
  const tvCount = tvCtx.data?.length ?? 0
  return tickerCount + researchCount + tvCount
}
