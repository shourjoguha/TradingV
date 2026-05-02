import { useState } from 'react'
import { Loader2, Send } from 'lucide-react'
import { Button } from '../ui/button'
import { Textarea } from '../ui/textarea'
import { Badge } from '../ui/badge'
import { useHypotheses } from '../../hooks/use-api'

interface Props {
  query: string
  setQuery: (q: string) => void
  scope: string[]
  setScope: (s: string[]) => void
  onSubmit: () => void
  isPending: boolean
}

export function AskInput({ query, setQuery, scope, setScope, onSubmit, isPending }: Props) {
  const { data: hyps } = useHypotheses({ status: 'active' })
  const items = hyps?.items ?? []

  const toggle = (slug: string) => {
    setScope(scope.includes(slug) ? scope.filter((s) => s !== slug) : [...scope, slug])
  }

  const canSubmit = query.trim().length > 0 && !isPending

  return (
    <div className="space-y-3">
      <Textarea
        placeholder="What's at risk in your active theses? e.g. 'Is the BTC bottom thesis weakening as DXY climbs?'"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        rows={3}
        disabled={isPending}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && canSubmit) onSubmit()
        }}
      />
      {items.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            Scope (optional — empty = all active)
          </div>
          <div className="flex flex-wrap gap-2">
            {items.map((h) => {
              const active = scope.includes(h.slug)
              return (
                <button
                  key={h.slug}
                  type="button"
                  onClick={() => toggle(h.slug)}
                  className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet rounded-full"
                  disabled={isPending}
                >
                  <Badge
                    variant={active ? 'default' : 'outline'}
                    className="cursor-pointer select-none"
                  >
                    {h.slug}
                  </Badge>
                </button>
              )
            })}
          </div>
        </div>
      )}
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          ⌘/Ctrl + Enter to submit. Latency ~3-8s.
        </div>
        <Button onClick={onSubmit} disabled={!canSubmit}>
          {isPending ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Asking…
            </>
          ) : (
            <>
              <Send className="h-4 w-4 mr-2" />
              Ask
            </>
          )}
        </Button>
      </div>
    </div>
  )
}
