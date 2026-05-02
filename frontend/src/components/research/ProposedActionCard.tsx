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
    <div className="rounded-2xl shadow-extruded-sm bg-background p-4 space-y-3 border-2 border-violet/20">
      <div className="flex items-center gap-2">
        <Wand2 className="h-4 w-4 text-violet" />
        <div className="text-sm font-medium">Proposed action</div>
        {status === 'approved' && <Badge variant="default">approved</Badge>}
        {status === 'dismissed' && <Badge variant="outline">dismissed</Badge>}
        {status === 'pending' && <Badge variant="outline">pending</Badge>}
        <div className="ml-auto text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          confidence {(proposed.confidence ?? 0).toFixed(2)}
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Hypothesis</span>
        <Badge variant="default">{proposed.hypothesis_slug}</Badge>
      </div>

      <div className="space-y-1">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          Op
        </div>
        <pre className="rounded-xl shadow-inset-sm bg-background p-2 text-[11px] font-mono whitespace-pre-wrap break-all">
          {proposed.proposed_invalidator.op}{'  '}
          {JSON.stringify(proposed.proposed_invalidator.args)}
        </pre>
      </div>

      <div className="space-y-1">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          Rationale
        </div>
        <div className="text-xs text-foreground/90 leading-relaxed">
          {proposed.rationale}
        </div>
      </div>

      {!isFinal && (
        <div className="flex items-center gap-2 pt-1">
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
