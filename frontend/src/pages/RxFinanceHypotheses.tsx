import { useHypothesisHealth } from '../hooks/use-api'
import { Skeleton } from '../components/ui/skeleton'
import { Badge } from '../components/ui/badge'
import { Brain } from 'lucide-react'
import { StatusBadge } from '../components/common/StatusBadge'
import { PageHeader } from '../components/common/PageHeader'

// Status colors migrated to <StatusBadge kind="hypothesis"> (Phase 1 unify).

/**
 * Time-to-expiry encoding (2026-05-17 color taxonomy). 3-tier ramp gives
 * the operator a pre-attentive "how urgent" channel orthogonal to the
 * status badge. mint > 30d / amber 7-30d / vermillion < 7d / brick = expired.
 * Replaces the previous 2-tier raw-Tailwind treatment (text-red-600 /
 * text-amber-600) which was off-palette.
 */
function expiryClass(days: number): string {
  if (days < 0)  return 'text-identity-stress font-semibold'
  if (days < 7)  return 'text-danger-fg font-semibold'
  if (days < 30) return 'text-warning-fg'
  return 'text-success-fg'
}

function expiryLabel(days: number): string {
  if (days < 0) return 'expired'
  return `${days}d`
}

export function RxFinanceHypotheses() {
  const q = useHypothesisHealth({ limit: 200 })
  // Only render the "Recent recs" column when at least one hypothesis
  // actually has a substring match. Otherwise the column is dead UI
  // (the heuristic is title-substring + 30d window — sparse by design).
  const showRecsColumn = (q.data?.items ?? []).some((h) => h.related_recs_count > 0)

  return (
    <div className="space-y-4">
      <PageHeader
        icon={Brain}
        title="Hypothesis health"
        description="Substring heuristic links hypotheses to recent finance recs (last 30 days)."
      />

      {q.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : (q.data?.items.length ?? 0) === 0 ? (
        <div className="rounded-3xl shadow-inset-sm p-8 text-center text-muted-foreground bg-background">
          <Brain className="h-8 w-8 mb-2 mx-auto text-muted-foreground/50" />
          <p className="text-sm">No hypotheses logged.</p>
        </div>
      ) : (
        <div className="rounded-2xl bg-background shadow-inset-sm p-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Title</th>
                <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Status</th>
                <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Age</th>
                <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Expires in</th>
                {showRecsColumn && (
                  <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Recent recs</th>
                )}
              </tr>
            </thead>
            <tbody>
              {q.data!.items.map((h) => {
                // Invalidated rows get a 3px identity-stress left-bar
                // (cell-level — table rows can't host pseudo-borders
                // cleanly under our transparent-border global rule).
                const invalidated = h.status === 'invalidated'
                return (
                <tr key={h.id} className="border-t border-border/40">
                  <td className="px-3 py-2 relative">
                    {invalidated && (
                      <div
                        aria-hidden
                        className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r bg-identity-stress"
                      />
                    )}
                    <div className={`font-medium ${invalidated ? 'line-through text-muted-foreground' : ''}`}>
                      {h.title}
                    </div>
                    <div className="text-xs font-mono text-muted-foreground">{h.slug} · {h.claim_type}</div>
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge kind="hypothesis" value={h.status} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs">{h.age_days}d</td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs">
                    <span className={expiryClass(h.days_to_expiry)}>
                      {expiryLabel(h.days_to_expiry)}
                    </span>
                  </td>
                  {showRecsColumn && (
                    <td className="px-3 py-2 text-right tabular-nums">
                      {h.related_recs_count > 0 ? (
                        <Badge variant="outline">{h.related_recs_count}</Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  )}
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
