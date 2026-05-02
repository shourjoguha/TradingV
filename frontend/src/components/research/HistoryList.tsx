import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { ResearchQueryRead } from '../../lib/types'
import { Badge } from '../ui/badge'
import { AnswerCard } from './AnswerCard'

interface Props {
  items: ResearchQueryRead[]
  filter: string
  setFilter: (s: string) => void
}

const FILTERS: Array<{ id: string; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'dismissed', label: 'Dismissed' },
]

export function HistoryList({ items, filter, setFilter }: Props) {
  const [openId, setOpenId] = useState<string | null>(null)

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
        <div className="space-y-2">
          {items.map((item) => {
            const isOpen = openId === item.id
            const Chevron = isOpen ? ChevronDown : ChevronRight
            const date = new Date(item.asked_at).toLocaleString()
            return (
              <div
                key={item.id}
                className="rounded-2xl shadow-extruded-sm bg-background"
              >
                <button
                  type="button"
                  onClick={() => setOpenId(isOpen ? null : item.id)}
                  className="w-full flex items-start gap-2 p-3 text-left"
                >
                  <Chevron className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
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
                    <div className="text-sm text-foreground/90 line-clamp-2">
                      {item.query}
                    </div>
                  </div>
                </button>
                {isOpen && (
                  <div className="p-3 pt-0">
                    <AnswerCard response={item} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
