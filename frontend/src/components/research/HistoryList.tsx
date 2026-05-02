import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import type { ResearchQueryRead } from '../../lib/types'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '../ui/accordion'
import { AnswerCard } from './AnswerCard'
import { ConfirmDeleteModal } from './ConfirmDeleteModal'

interface Props {
  items: ResearchQueryRead[]
  filter: string
  setFilter: (s: string) => void
  hasMore: boolean
  loading: boolean
  onLoadMore: () => void
}

const FILTERS: Array<{ id: string; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'dismissed', label: 'Dismissed' },
]

export function HistoryList({
  items,
  filter,
  setFilter,
  hasMore,
  loading,
  onLoadMore,
}: Props) {
  const [deleteTarget, setDeleteTarget] = useState<ResearchQueryRead | null>(null)

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mr-1">
          Status
        </div>
        {FILTERS.map((f) => (
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

      {items.length === 0 ? (
        <div className="rounded-2xl shadow-inset-sm bg-background p-4 text-xs text-muted-foreground">
          No queries yet for this filter.
        </div>
      ) : (
        <Accordion type="single" collapsible className="space-y-2">
          {items.map((item) => {
            const date = new Date(item.asked_at).toLocaleString()
            return (
              <AccordionItem
                key={item.id}
                value={item.id}
                className="relative shadow-extruded-sm"
              >
                <AccordionTrigger className="pr-12">
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {date}
                      </span>
                      <Badge
                        variant={
                          item.status === 'approved'
                            ? 'default'
                            : item.status === 'error'
                              ? 'destructive'
                              : 'outline'
                        }
                        className="text-[10px]"
                      >
                        {item.status}
                      </Badge>
                      {(item.hypothesis_ids ?? []).map((h) => (
                        <Badge
                          key={h}
                          variant="outline"
                          className="text-[10px] font-mono"
                        >
                          {h}
                        </Badge>
                      ))}
                    </div>
                    <div className="text-sm text-foreground/90 line-clamp-2 break-words">
                      {item.query}
                    </div>
                  </div>
                </AccordionTrigger>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setDeleteTarget(item)
                  }}
                  className="absolute top-2 right-2 p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive"
                  aria-label="Delete query"
                  title="Delete query"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
                <AccordionContent>
                  <AnswerCard response={item} />
                </AccordionContent>
              </AccordionItem>
            )
          })}
        </Accordion>
      )}

      {hasMore && items.length > 0 && (
        <div className="flex justify-center pt-1">
          <Button
            variant="outline"
            size="sm"
            onClick={onLoadMore}
            disabled={loading}
          >
            {loading ? 'Loading…' : 'Load more'}
          </Button>
        </div>
      )}

      <ConfirmDeleteModal
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        queryId={deleteTarget?.id ?? ''}
        queryText={deleteTarget?.query ?? ''}
      />
    </div>
  )
}
