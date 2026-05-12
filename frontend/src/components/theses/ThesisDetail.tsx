import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Sparkles, X } from 'lucide-react'
import {
  useHypothesis,
  useCancelHypothesis,
  useResearchAsk,
} from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { Skeleton } from '../ui/skeleton'
import { EvaluationRow } from './EvaluationRow'
import { toast } from 'sonner'

interface Props {
  hypothesisId: string | null
}

/**
 * Detail panel for a single hypothesis.
 *
 * Renders body markdown + recent evaluations + action buttons:
 * - "Stress this thesis" → POST /v1/research/ask with hypothesis_slugs;
 *   navigates the operator to /research?id={query_id} on success.
 * - "Cancel" → opens a tiny inline reason input then POST /cancel.
 */
export function ThesisDetail({ hypothesisId }: Props) {
  const { data: h, isLoading } = useHypothesis(hypothesisId)
  const stress = useResearchAsk()
  const cancel = useCancelHypothesis()
  const navigate = useNavigate()
  const [cancelReason, setCancelReason] = useState('')
  const [showCancel, setShowCancel] = useState(false)

  if (!hypothesisId) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground italic">
          Select a thesis to inspect.
        </CardContent>
      </Card>
    )
  }
  if (isLoading || !h) {
    return (
      <Card>
        <CardContent className="py-8">
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    )
  }

  const onStress = () => {
    stress.mutate(
      {
        query: `Stress-test the hypothesis "${h.title}" against current evidence.`,
        hypothesis_slugs: [h.slug],
      },
      {
        onSuccess: (resp) => {
          toast.success('Stress-test queued')
          navigate(`/research?id=${resp.query_id}`)
        },
      },
    )
  }

  const onCancel = () => {
    if (!cancelReason.trim()) {
      toast.error('Please provide a cancellation reason.')
      return
    }
    cancel.mutate(
      { id: h.id, reason: cancelReason.trim() },
      {
        onSuccess: () => {
          toast.success('Thesis cancelled')
          setShowCancel(false)
          setCancelReason('')
        },
      },
    )
  }

  return (
    <Card>
      <CardHeader className="space-y-2 pb-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-base">{h.title}</CardTitle>
          <Badge variant="outline" className="shrink-0 text-[10px]">
            {h.status}
          </Badge>
        </div>
        <div className="flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
          <span className="font-mono">{h.slug}</span>
          <span>·</span>
          <span>{h.axis}</span>
          <span>·</span>
          <span>{h.claim_type}</span>
          <span>·</span>
          <span>expires {new Date(h.expires_at).toLocaleDateString()}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {h.body_md && (
          <div className="prose prose-sm max-w-none text-foreground/90 leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{h.body_md}</ReactMarkdown>
          </div>
        )}

        <div className="flex items-center gap-2 flex-wrap">
          <Button
            size="sm"
            onClick={onStress}
            disabled={stress.isPending || h.status !== 'active'}
          >
            <Sparkles className="h-3 w-3 mr-1" />
            Stress this thesis
          </Button>
          {h.status === 'active' &&
            (showCancel ? (
              <div className="flex items-center gap-2 flex-1">
                <input
                  value={cancelReason}
                  onChange={(e) => setCancelReason(e.target.value)}
                  placeholder="Why cancel?"
                  className="flex-1 min-w-[10rem] rounded-2xl shadow-inset-sm bg-background px-3 py-1.5 text-xs"
                />
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={onCancel}
                  disabled={cancel.isPending}
                >
                  Confirm
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setShowCancel(false)
                    setCancelReason('')
                  }}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowCancel(true)}
                disabled={cancel.isPending}
              >
                Cancel
              </Button>
            ))}
        </div>

        {h.recent_evaluations && h.recent_evaluations.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              Recent evaluations ({h.recent_evaluations.length})
            </div>
            {h.recent_evaluations.map((e) => (
              <EvaluationRow key={e.id} evaluation={e} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
