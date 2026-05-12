import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FlaskConical } from 'lucide-react'
import type { HypothesisStatus } from '../lib/types'
import { ThesesList } from '../components/theses/ThesesList'
import { ThesisDetail } from '../components/theses/ThesisDetail'
import { useHypothesisSummary } from '../hooks/use-api'
import { Badge } from '../components/ui/badge'

const STATUS_FILTERS: Array<{ id: HypothesisStatus | 'all'; label: string }> = [
  { id: 'active', label: 'Active' },
  { id: 'expired', label: 'Expired' },
  { id: 'invalidated', label: 'Invalidated' },
  { id: 'cancelled', label: 'Cancelled' },
  { id: 'manual_closed', label: 'Manual closed' },
  { id: 'all', label: 'All' },
]

/**
 * Theses — `/theses`
 *
 * First-class hypothesis surface. Two-column on desktop: filterable
 * list + detail panel. Detail "Stress this thesis" deep-links into
 * /research with a stress-test query queued.
 *
 * Phase 3 IA reorg.
 */
export function Theses() {
  const [search, setSearch] = useSearchParams()
  const initialId = search.get('id')
  const [filter, setFilter] = useState<HypothesisStatus | 'all'>('active')
  const [selectedId, setSelectedId] = useState<string | null>(initialId)
  const summary = useHypothesisSummary()

  useEffect(() => {
    if (initialId && initialId !== selectedId) {
      setSelectedId(initialId)
    }
  }, [initialId, selectedId])

  const onSelect = (id: string) => {
    setSelectedId(id)
    const next = new URLSearchParams(search)
    next.set('id', id)
    setSearch(next, { replace: true })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
            <FlaskConical className="h-6 w-6 text-violet" />
            Theses
          </h2>
          <p className="text-muted-foreground text-sm">
            Hypotheses tracking the regime + names. Stress them into Research,
            cancel when invalidated.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {summary.data && (
            <>
              <Badge variant="outline" className="bg-success-bg text-success-fg">
                {summary.data.active} active
              </Badge>
              {summary.data.at_risk > 0 && (
                <Badge variant="outline" className="bg-warning-bg text-warning-fg">
                  {summary.data.at_risk} at risk
                </Badge>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mr-1">
          Status
        </div>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet rounded-full"
          >
            <Badge
              variant={filter === f.id ? 'default' : 'outline'}
              className="cursor-pointer select-none"
            >
              {f.label}
            </Badge>
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
        <ThesesList
          status={filter === 'all' ? undefined : filter}
          selectedId={selectedId}
          onSelect={onSelect}
        />
        <ThesisDetail hypothesisId={selectedId} />
      </div>
    </div>
  )
}
