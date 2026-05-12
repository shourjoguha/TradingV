import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles, ChevronDown, ChevronRight, ArrowRight } from 'lucide-react'
import {
  useResearchQueries,
  useApproveResearchQuery,
  useDismissResearchQuery,
} from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'

/**
 * Bottom-of-Today "Pending review" panel.
 *
 * Compressed view: top-5 by composite score (server-side ranking),
 * collapsed by default. Click a row → inline expand to verdict + inline
 * Approve/Dismiss buttons. No modal hop. Footer shows backlog count +
 * link to full queue.
 *
 * Two queries: top-5 visible (include_deferred=false) + full-pending
 * count (include_deferred=true, limit=200) so the "of N" total is
 * accurate without paging.
 */
export function PendingReviewPanel() {
  const top = useResearchQueries({
    status: 'pending',
    order: 'score',
    includeDeferred: false,
    limit: 5,
  })
  const all = useResearchQueries({
    status: 'pending',
    includeDeferred: true,
    limit: 200,
  })
  const approve = useApproveResearchQuery()
  const dismiss = useDismissResearchQuery()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (top.isLoading) return null
  const items = top.data?.items ?? []
  if (items.length === 0) return null

  const totalPending = all.data?.items?.length ?? items.length
  const backlogCount = Math.max(0, totalPending - items.length)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-violet" />
          Pending review · top {items.length} of {totalPending}
        </CardTitle>
        <Link
          to="/research?status=pending"
          className="text-xs text-muted-foreground hover:text-violet"
        >
          Open queue
        </Link>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {items.map((q) => {
          const isExpanded = expandedId === q.id
          const isWorking =
            (approve.isPending && approve.variables === q.id) ||
            (dismiss.isPending && dismiss.variables === q.id)
          const verdictSnippet =
            q.verdict?.replace(/[#*_>`]/g, '').slice(0, 200) ?? null
          const hypSlug = q.hypothesis_ids?.[0] ?? null

          return (
            <div
              key={q.id}
              className="rounded-2xl shadow-inset-sm bg-background"
            >
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : q.id)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left"
                aria-expanded={isExpanded}
              >
                {isExpanded ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{q.query}</div>
                  {hypSlug && (
                    <div className="text-[10px] font-mono text-muted-foreground truncate">
                      {hypSlug}
                    </div>
                  )}
                </div>
                {q.score != null && (
                  <Badge variant="outline" className="text-[10px] shrink-0">
                    score {q.score.toFixed(1)}
                  </Badge>
                )}
                <Badge variant="outline" className="text-[10px] shrink-0">
                  {new Date(q.asked_at).toLocaleDateString()}
                </Badge>
              </button>
              {isExpanded && (
                <div className="px-3 pb-3 pt-1 space-y-2 border-t border-border/40">
                  {verdictSnippet && (
                    <div className="text-xs text-muted-foreground whitespace-pre-wrap">
                      {verdictSnippet}
                    </div>
                  )}
                  <div className="flex items-center gap-2 flex-wrap">
                    <Button
                      size="sm"
                      disabled={isWorking}
                      onClick={() => approve.mutate(q.id)}
                      className="h-7 px-3 text-xs"
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={isWorking}
                      onClick={() => dismiss.mutate(q.id)}
                      className="h-7 px-3 text-xs"
                    >
                      Dismiss
                    </Button>
                    <Link
                      to={`/research?id=${q.id}`}
                      className="ml-auto text-xs text-muted-foreground hover:text-violet flex items-center gap-1"
                    >
                      Open detail <ArrowRight className="h-3 w-3" />
                    </Link>
                  </div>
                </div>
              )}
            </div>
          )
        })}
        {backlogCount > 0 && (
          <Link
            to="/research?status=pending"
            className="block text-xs text-muted-foreground hover:text-violet pt-1"
          >
            See full queue ({backlogCount} more in backlog) →
          </Link>
        )}
      </CardContent>
    </Card>
  )
}
