import { Link } from 'react-router-dom'
import { FileSearch, ArrowRight } from 'lucide-react'
import { useResearchQueries } from '../../hooks/use-api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'

/**
 * Today landing card: research curiosity preview.
 *
 * Shows pending-query count + top hypothesis being stress-tested. No
 * inline Approve/Dismiss buttons — those live in the bottom-of-page
 * PendingReviewPanel and on /research. This card is preview-only.
 *
 * Uses the include_deferred=false filter so the count reflects only
 * the currently-visible top cohort (not the deferred backlog). Footer
 * link in PendingReviewPanel handles the backlog navigation.
 */
export function ResearchCuriousCard() {
  // Pull all visible pending (top 5) — gives accurate "count + top hypothesis"
  // without bringing in the deferred queue.
  const { data, isLoading } = useResearchQueries({
    status: 'pending',
    order: 'score',
    includeDeferred: false,
    limit: 5,
  })
  const items = data?.items ?? []
  const top = items[0]
  const topHyp = top?.hypothesis_ids?.[0] ?? null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <FileSearch className="h-4 w-4 text-violet" />
          What it's curious about
        </CardTitle>
        <CardDescription className="text-xs">
          Stress-test questions the operator has queued against the curated
          knowledge vault — ranked by hypothesis at-risk + cost paid.
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <p className="text-xs text-muted-foreground">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No active research queries. Submit one from the Research page or
            wait for the next weekly auto-stress tick.
          </p>
        ) : (
          <div className="space-y-1.5">
            <div className="flex items-baseline gap-2 text-sm">
              <span className="font-display text-lg font-semibold">{items.length}</span>
              <span className="text-xs text-muted-foreground">
                pending review {items.length === 5 && '(top 5 shown below)'}
              </span>
            </div>
            {topHyp && (
              <div className="font-mono text-xs text-muted-foreground truncate">
                Top: <span className="text-foreground font-semibold">{topHyp}</span>
              </div>
            )}
            <Link
              to="/research?status=pending"
              className="inline-flex items-center gap-1 text-xs text-violet hover:text-violet/80"
            >
              Open research <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
