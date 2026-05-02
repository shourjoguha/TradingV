import { useState } from 'react'
import { Check, X, Wand2 } from 'lucide-react'
import type { ProposedAction } from '../../lib/types'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { ConfirmApproveModal } from './ConfirmApproveModal'
import { useDismissResearchQuery } from '../../hooks/use-api'

interface Props {
  queryId: string
  proposed: ProposedAction
  status: 'pending' | 'approved' | 'dismissed' | 'error'
}

export function ProposedActionCard({ queryId, proposed, status }: Props) {
  const [modalOpen, setModalOpen] = useState(false)
  const dismiss = useDismissResearchQuery()
  const isFinal = status === 'approved' || status === 'dismissed'

  return (
    <div className="rounded-2xl shadow-extruded-sm bg-background p-3 space-y-2 border-2 border-violet/20">
      <div className="flex items-center gap-2 flex-wrap">
        <Wand2 className="h-4 w-4 text-violet shrink-0" />
        <div className="text-sm font-medium">Proposed action</div>
        <Badge variant="default" className="font-mono text-[10px]">
          {proposed.hypothesis_slug}
        </Badge>
        <div className="ml-auto text-[10px] font-mono uppercase tracking-wider text-muted-foreground tabular-nums">
          conf {(proposed.confidence ?? 0).toFixed(2)}
        </div>
      </div>

      <pre className="rounded-xl shadow-inset-sm bg-background p-2 text-[10px] font-mono whitespace-pre-wrap break-all">
        {proposed.proposed_invalidator.op}
        {'  '}
        {JSON.stringify(proposed.proposed_invalidator.args)}
      </pre>

      <div className="text-xs text-foreground/90 leading-relaxed">
        {proposed.rationale}
      </div>

      {!isFinal && (
        <div className="flex items-center gap-2 pt-0.5">
          <Button size="sm" onClick={() => setModalOpen(true)}>
            <Check className="h-4 w-4 mr-1.5" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => dismiss.mutate(queryId)}
            disabled={dismiss.isPending}
          >
            <X className="h-4 w-4 mr-1.5" />
            Dismiss
          </Button>
        </div>
      )}

      <ConfirmApproveModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        queryId={queryId}
        proposed={proposed}
      />
    </div>
  )
}
