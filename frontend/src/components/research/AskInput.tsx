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
    <div className="space-y-2">
      <Textarea
        placeholder="What's at risk in your active theses? e.g. 'Is the BTC bottom thesis weakening as DXY climbs?'"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        rows={2}
        disabled={isPending}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && canSubmit) onSubmit()
        }}
      />
      {items.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground shrink-0">
            Scope:{scope.length === 0 && <span className="ml-1">all</span>}
          </span>
          {items.map((h) => {
            const active = scope.includes(h.slug)
            return (
              <button
                key={h.slug}
                type="button"
                onClick={() => toggle(h.slug)}
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-full"
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
      )}
    </div>
  )
}
