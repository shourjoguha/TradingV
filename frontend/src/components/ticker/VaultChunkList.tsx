import { useState } from 'react'
import { BookOpen, ChevronDown, ChevronRight } from 'lucide-react'
import { useVaultSearch } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import type { VaultSearchHit } from '../../lib/types'

interface Props {
  symbol: string
  k?: number
}

/**
 * Vault chunks for a ticker — calls `/v1/vault/search?q=<symbol>` and
 * renders the top-K matches.
 *
 * Each card shows the **extractive teaser** (top 2 sentences from the
 * chunk most relevant to the query, computed server-side via the BGE
 * encoder — see `tools/vault_indexer/excerpt.py`). Click to expand the
 * full chunk body inline.
 *
 * Degrades gracefully when the vault-indexer is offline (502 from proxy)
 * by hiding the section instead of showing an error chrome.
 */
export function VaultChunkList({ symbol, k = 6 }: Props) {
  const { data, isLoading, isError } = useVaultSearch(symbol, k)
  if (isError) return null

  const hits = data?.results ?? []

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-primary" />
          Vault chunks
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading ? (
          <div className="text-xs text-muted-foreground italic">Loading…</div>
        ) : hits.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No vault matches for {symbol}.
          </div>
        ) : (
          hits.map((h, i) => <ChunkRow key={`${h.path}-${i}`} hit={h} />)
        )}
      </CardContent>
    </Card>
  )
}

function ChunkRow({ hit }: { hit: VaultSearchHit }) {
  const [open, setOpen] = useState(false)
  const teaser = hit.excerpt_sentences ?? []
  const hasTeaser = teaser.length > 0
  const teaserText = teaser.join(' ')
  const fileName = hit.path.split('/').pop() ?? hit.path
  const folder = hit.path.includes('/')
    ? hit.path.slice(0, hit.path.lastIndexOf('/'))
    : ''

  return (
    <div className="rounded-2xl shadow-inset-sm bg-background p-3 space-y-1 min-w-0">
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="text-xs font-medium truncate min-w-0 flex-1">
          {hit.title || fileName}
          {hit.section && (
            <span className="text-muted-foreground"> · {hit.section}</span>
          )}
        </div>
        <Badge
          variant="outline"
          className="text-xs shrink-0 tabular-nums"
          title={`similarity ${hit.similarity.toFixed(2)} · decay ${hit.decay_weight.toFixed(2)}`}
        >
          {hit.score.toFixed(2)}
        </Badge>
      </div>

      <div
        className="text-xs font-mono text-muted-foreground truncate"
        title={hit.path}
      >
        {folder || hit.path}
      </div>

      {hasTeaser ? (
        <div className="text-xs text-muted-foreground break-words leading-relaxed">
          {teaserText}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground line-clamp-3 break-words">
          {hit.text}
        </div>
      )}

      {hasTeaser && hit.text && hit.text.length > teaserText.length + 20 && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1"
        >
          {open ? (
            <>
              <ChevronDown className="h-3 w-3" />
              Hide full chunk
            </>
          ) : (
            <>
              <ChevronRight className="h-3 w-3" />
              Show full chunk
            </>
          )}
        </button>
      )}

      {open && hasTeaser && (
        <div className="text-xs text-muted-foreground break-words leading-relaxed pt-2 border-t border-foreground/5">
          {hit.text}
        </div>
      )}
    </div>
  )
}
