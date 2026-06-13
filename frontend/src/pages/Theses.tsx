import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { FlaskConical, Sparkles, X } from 'lucide-react'
import type { HypothesisStatus } from '../lib/types'
import { ThesesList } from '../components/theses/ThesesList'
import { ThesisDetail } from '../components/theses/ThesisDetail'
import { useHypotheses, useHypothesisSummary } from '../hooks/use-api'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { InfoBubble } from '../components/common'

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
  // Promote-to-thesis deep-link from rec detail (RxFinanceDetail). Both
  // params survive the lifetime of this view until the operator dismisses
  // the banner.
  const fromRec = search.get('from_rec')
  const fromTicker = search.get('ticker')
  const [filter, setFilter] = useState<HypothesisStatus | 'all'>('active')
  const [selectedId, setSelectedId] = useState<string | null>(initialId)
  const summary = useHypothesisSummary()

  // When a ticker is in the URL, search all hypotheses for title matches —
  // gives the operator an "is there already a thesis for this?" answer
  // before they author a new one. Title substring match w/ uppercase
  // normalisation (tickers are uppercase).
  const allActive = useHypotheses({ status: 'active' })
  const matchingExisting = useMemo(() => {
    if (!fromTicker) return []
    const needle = fromTicker.toUpperCase()
    return (allActive.data?.items ?? []).filter((h) =>
      (h.title || '').toUpperCase().includes(needle),
    )
  }, [fromTicker, allActive.data])

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

  const dismissBanner = () => {
    const next = new URLSearchParams(search)
    next.delete('from_rec')
    next.delete('ticker')
    setSearch(next, { replace: true })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
            <FlaskConical className="h-6 w-6 text-primary" />
            Theses
            <InfoBubble
              label="About Theses"
              size={14}
              content="Hypotheses tracking the regime + names. Stress them into Research, cancel when invalidated."
            />
          </h2>
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

      {/* Promote-to-thesis prefill banner — appears when arriving via
          /theses?from_rec=...&ticker=... from a rec detail page. Surfaces
          matching existing hypotheses + draft-author hint. */}
      {fromRec && (
        <div className="rounded-2xl shadow-inset-sm bg-primary/5 border border-primary/20 p-4 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <Sparkles className="h-4 w-4 text-primary" />
                <span className="font-medium text-sm">Author thesis from rec</span>
                <Link
                  to={`/motion/recs/${fromRec}`}
                  className="font-mono text-xs text-primary hover:underline"
                >
                  {fromRec.slice(0, 8)}
                </Link>
                {fromTicker && (
                  <Badge variant="outline" className="font-mono text-xs">
                    {fromTicker}
                  </Badge>
                )}
              </div>
              {matchingExisting.length > 0 ? (
                <div className="text-xs text-muted-foreground">
                  Found {matchingExisting.length} active thesis{matchingExisting.length === 1 ? '' : 'es'} mentioning <span className="font-mono">{fromTicker}</span> — click one below to update it, or author a new draft.
                </div>
              ) : (
                <div className="text-xs text-muted-foreground">
                  No active thesis mentions <span className="font-mono">{fromTicker}</span> yet. Author a new draft at <code className="text-[11px]">~/Documents/Sho's Playgroun/Lakshmi/02_library/theses/&lt;slug&gt;.md</code>, then commit. Hypothesis ingest will pick it up.
                </div>
              )}
              {matchingExisting.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {matchingExisting.map((h) => (
                    <button
                      key={h.id}
                      type="button"
                      onClick={() => onSelect(h.id)}
                      className="text-[11px] px-2 py-1 rounded-full bg-background shadow-inset-sm hover:shadow-extruded-sm transition-all max-w-[20rem] truncate text-left"
                      title={h.title}
                    >
                      {h.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <Button variant="ghost" size="sm" onClick={dismissBanner} aria-label="Dismiss">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <div className="text-xs font-mono text-muted-foreground mr-1">
          Status
        </div>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-full"
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
