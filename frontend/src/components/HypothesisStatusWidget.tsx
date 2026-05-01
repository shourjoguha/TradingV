import { useHypothesisSummary } from '../hooks/use-api'
import { Lightbulb, AlertCircle } from 'lucide-react'

// Sidebar widget — at-a-glance counts of active hypotheses + at-risk ones.
// Lives at the bottom of the sidebar so it's always visible without
// disturbing the nav. M-2 minimum-viable surface (no full /hypotheses page
// yet — operator decision: defer page until ≥10 active rows).
export function HypothesisStatusWidget() {
  const { data, isLoading } = useHypothesisSummary()
  if (isLoading) {
    return (
      <div className="mx-3 mb-3 rounded-2xl bg-background shadow-inset-sm p-3">
        <div className="h-4 w-20 bg-muted rounded animate-pulse" />
      </div>
    )
  }
  if (!data) return null
  const active = data.active ?? 0
  const atRisk = data.at_risk ?? 0
  const total = active + (data.expired ?? 0) + (data.invalidated ?? 0) + (data.cancelled ?? 0) + (data.manual_closed ?? 0)
  // Hide widget entirely until first hypothesis exists. No noise.
  if (total === 0) return null

  return (
    <div className="mx-3 mb-3 rounded-2xl bg-background shadow-inset-sm p-3 space-y-1.5">
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
        <Lightbulb className="h-3 w-3" />
        Hypotheses
      </div>
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-mono text-muted-foreground">active</span>
        <span className="text-sm font-mono font-bold tabular-nums">{active}</span>
      </div>
      {atRisk > 0 && (
        <div className="flex items-baseline justify-between text-warning-fg">
          <span className="inline-flex items-center gap-1 text-xs font-mono">
            <AlertCircle className="h-3 w-3" />
            at risk
          </span>
          <span className="text-sm font-mono font-bold tabular-nums">{atRisk}</span>
        </div>
      )}
      <div className="text-[10px] font-mono text-muted-foreground/70">
        TTL ≤ 30d ahead
      </div>
    </div>
  )
}
