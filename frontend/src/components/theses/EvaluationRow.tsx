import type { HypothesisEvaluation } from '../../lib/types'
import { Badge } from '../ui/badge'

interface Props {
  evaluation: HypothesisEvaluation
}

export function EvaluationRow({ evaluation }: Props) {
  const transitioned = evaluation.status_before !== evaluation.status_after
  return (
    <div className="rounded-2xl shadow-inset-sm bg-background px-3 py-2 text-xs space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-muted-foreground">
          {new Date(evaluation.evaluated_at).toLocaleString()}
        </span>
        <div className="flex items-center gap-1">
          <Badge variant="outline" className="text-[10px]">
            {evaluation.status_before}
          </Badge>
          {transitioned && (
            <>
              <span className="text-muted-foreground">→</span>
              <Badge variant="outline" className="text-[10px]">
                {evaluation.status_after}
              </Badge>
            </>
          )}
        </div>
      </div>
      {evaluation.reason && (
        <div className="text-muted-foreground line-clamp-2">{evaluation.reason}</div>
      )}
    </div>
  )
}
