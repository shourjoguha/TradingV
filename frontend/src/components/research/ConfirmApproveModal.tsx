import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import type { ProposedAction } from '../../lib/types'
import { useApproveResearchQuery, useHypothesis } from '../../hooks/use-api'
import { apiFetch } from '../../lib/api'
import { useBackend } from '../../hooks/use-backend'
import { useQuery } from '@tanstack/react-query'
import type { Hypothesis } from '../../lib/types'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  queryId: string
  proposed: ProposedAction
  onApproved?: () => void
}

// Look up the hypothesis by slug (the existing useHypothesis takes id).
function useHypothesisBySlug(slug: string | null) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['hypothesis-by-slug', backendId, slug],
    queryFn: async () => {
      const list = await apiFetch<{ items: Hypothesis[] }>(
        `/v1/hypotheses?status=active`,
        { backendId },
      )
      return list.items.find((h) => h.slug === slug) ?? null
    },
    enabled: !!slug,
    staleTime: 60_000,
  })
}

export function ConfirmApproveModal({
  open,
  onOpenChange,
  queryId,
  proposed,
  onApproved,
}: Props) {
  const approve = useApproveResearchQuery()
  const { data: hyp } = useHypothesisBySlug(proposed.hypothesis_slug)

  const onApply = () => {
    approve.mutate(queryId, {
      onSuccess: () => {
        onOpenChange(false)
        onApproved?.()
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Apply proposed invalidator</DialogTitle>
          <DialogDescription>
            This mutates the hypothesis's invalidator DSL. Reversible by editing the
            hypothesis directly, but the change is logged.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <div className="space-y-1">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              Hypothesis
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="default">{proposed.hypothesis_slug}</Badge>
              {hyp ? (
                <span className="text-muted-foreground text-xs">{hyp.title}</span>
              ) : null}
            </div>
          </div>

          {hyp && (
            <div className="space-y-1">
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                Current invalidator
              </div>
              <pre className="rounded-2xl shadow-inset-sm bg-background p-3 text-[11px] font-mono whitespace-pre-wrap break-all">
                {JSON.stringify(hyp.invalidator, null, 2)}
              </pre>
            </div>
          )}

          <div className="space-y-1">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              Proposed invalidator
            </div>
            <pre className="rounded-2xl shadow-inset-sm bg-background p-3 text-[11px] font-mono whitespace-pre-wrap break-all">
              {JSON.stringify(proposed.proposed_invalidator, null, 2)}
            </pre>
          </div>

          <div className="space-y-1">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              Rationale (Claude){' '}
              <span className="opacity-60">· confidence {(proposed.confidence ?? 0).toFixed(2)}</span>
            </div>
            <div className="text-foreground/90 text-xs leading-relaxed">
              {proposed.rationale}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={approve.isPending}>
            Cancel
          </Button>
          <Button onClick={onApply} disabled={approve.isPending}>
            {approve.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Applying…
              </>
            ) : (
              'Apply'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
