import { useHypotheses } from '../../hooks/use-api'
import type { Hypothesis, HypothesisStatus } from '../../lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { Skeleton } from '../ui/skeleton'

interface Props {
  status?: HypothesisStatus
  selectedId: string | null
  onSelect: (id: string) => void
}

const STATUS_TONE: Record<HypothesisStatus, string> = {
  active: 'bg-success-bg text-success-fg',
  expired: 'bg-warning-bg text-warning-fg',
  invalidated: 'bg-danger-bg text-danger-fg',
  cancelled: '',
  manual_closed: '',
}

/**
 * Filterable list of hypotheses. One-click selection drives the detail
 * panel. Status badge is color-toned so the operator can scan health.
 */
export function ThesesList({ status, selectedId, onSelect }: Props) {
  const { data, isLoading } = useHypotheses({ status })
  const items = data?.items ?? []

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Theses {status && <span className="text-muted-foreground">/ {status}</span>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : items.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No theses match this filter.
          </div>
        ) : (
          items.map((h: Hypothesis) => (
            <button
              key={h.id}
              type="button"
              onClick={() => onSelect(h.id)}
              className={`w-full text-left rounded-2xl px-3 py-2 transition-all ${
                selectedId === h.id
                  ? 'shadow-inset-sm bg-background'
                  : 'shadow-extruded-sm hover:shadow-extruded'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium truncate">{h.title}</span>
                <Badge
                  variant="outline"
                  className={`text-[10px] shrink-0 ${STATUS_TONE[h.status]}`}
                >
                  {h.status}
                </Badge>
              </div>
              <div className="text-xs text-muted-foreground truncate">
                {h.axis} · {h.claim_type} · expires{' '}
                {new Date(h.expires_at).toLocaleDateString()}
              </div>
            </button>
          ))
        )}
      </CardContent>
    </Card>
  )
}
