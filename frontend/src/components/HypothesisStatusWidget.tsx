import { Link } from 'react-router-dom'
import { useHypothesisSummary } from '../hooks/use-api'
import { Lightbulb, AlertCircle } from 'lucide-react'

/**
 * HypothesisStatusWidget — sidebar ambient pin showing active+at-risk.
 *
 * Phase 6 polish (designer P2-9): tightened to match RxStatusWidget's
 * compact treatment so widgets read as ambient, not primary.
 */
export function HypothesisStatusWidget() {
  const { data, isLoading } = useHypothesisSummary()
  if (isLoading || !data) return null
  const active = data.active ?? 0
  const atRisk = data.at_risk ?? 0
  const total = active + (data.expired ?? 0) + (data.invalidated ?? 0) + (data.cancelled ?? 0) + (data.manual_closed ?? 0)
  if (total === 0) return null

  return (
    <Link
      to="/theses"
      className="mx-3 mb-3 block rounded-xl px-3 py-2 hover:bg-muted/30 transition-all text-xs"
    >
      <div className="flex items-center justify-between text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Lightbulb className="h-3 w-3" />
          <span className="text-xs">theses</span>
        </span>
        <span className="tabular-nums text-foreground font-mono">{active}</span>
      </div>
      {atRisk > 0 && (
        <div className="flex items-center justify-between text-warning-fg mt-1">
          <span className="inline-flex items-center gap-1.5">
            <AlertCircle className="h-3 w-3" />
            <span className="text-xs">at risk</span>
          </span>
          <span className="tabular-nums font-mono">{atRisk}</span>
        </div>
      )}
    </Link>
  )
}
