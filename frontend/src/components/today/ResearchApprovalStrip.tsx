import { Link } from 'react-router-dom'
import { Sparkles, ArrowRight } from 'lucide-react'
import {
  useResearchQueries,
  useApproveResearchQuery,
  useDismissResearchQuery,
} from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'

/**
 * Pending Research approvals strip for the Today page.
 *
 * Lists research queries with status='pending' so the operator can clear
 * yesterday's stress-tests as the first morning task. Each row shows the
 * truncated query + verdict snippet, with inline Approve / Dismiss /
 * Open-detail. Full surface remains at `/research`.
 */
export function ResearchApprovalStrip() {
  const { data, isLoading } = useResearchQueries({ status: 'pending', limit: 10 })
  const approve = useApproveResearchQuery()
  const dismiss = useDismissResearchQuery()

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            Pending Research
          </CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground italic">
          Loading…
        </CardContent>
      </Card>
    )
  }

  const items = data?.items ?? []
  if (items.length === 0) return null

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          Pending Research ({items.length})
        </CardTitle>
        <Link to="/research" className="text-xs text-muted-foreground hover:text-primary">
          Open
        </Link>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.map((q) => {
          const isWorking =
            (approve.isPending && approve.variables === q.id) ||
            (dismiss.isPending && dismiss.variables === q.id)
          const verdictSnippet =
            q.verdict?.replace(/[#*_>`]/g, '').slice(0, 140) ?? null
          return (
            <div
              key={q.id}
              className="rounded-2xl shadow-inset-sm bg-background p-3 space-y-2"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{q.query}</div>
                  {verdictSnippet && (
                    <div className="text-xs text-muted-foreground line-clamp-2 mt-1">
                      {verdictSnippet}
                    </div>
                  )}
                </div>
                <Badge variant="outline" className="shrink-0 text-xs">
                  {new Date(q.asked_at).toLocaleDateString()}
                </Badge>
              </div>
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
                  className="ml-auto text-xs text-muted-foreground hover:text-primary flex items-center gap-1"
                >
                  Detail <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
