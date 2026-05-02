import { useState } from 'react'
import { ChevronRight, ExternalLink } from 'lucide-react'
import type { EvidenceItem } from '../../lib/types'
import { Badge } from '../ui/badge'

interface Props {
  item: EvidenceItem
  vaultName?: string
}

function obsidianUri(vaultPath: string, vaultName: string): string {
  // Strip .md if present (Obsidian appends one).
  const file = vaultPath.replace(/\.md$/i, '')
  return `obsidian://open?vault=${encodeURIComponent(vaultName)}&file=${encodeURIComponent(file)}`
}

export function EvidenceItemRow({ item, vaultName = 'knowledge-vault' }: Props) {
  const [expanded, setExpanded] = useState(false)
  const uri = obsidianUri(item.vault_path, vaultName)
  const label = item.title || item.vault_path.split('/').pop() || item.vault_path

  return (
    <div className="rounded-2xl shadow-inset-sm bg-background p-3 space-y-2">
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-0.5 text-muted-foreground hover:text-foreground transition"
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          <ChevronRight
            className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-90' : ''}`}
          />
        </button>
        <div className="flex-1 min-w-0">
          <a
            href={uri}
            className="font-medium text-sm text-foreground hover:text-violet inline-flex items-center gap-1 break-all"
            title="Open in Obsidian"
          >
            {label}
            <ExternalLink className="h-3 w-3 shrink-0" />
          </a>
          <div className="text-[11px] font-mono text-muted-foreground mt-0.5 break-all">
            {item.vault_path}
            {item.section ? ` › ${item.section}` : ''}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Badge variant="outline" className="text-[10px] tabular-nums">
            score {item.score.toFixed(3)}
          </Badge>
          <Badge variant="outline" className="text-[10px] tabular-nums">
            sim {item.similarity.toFixed(2)}
          </Badge>
          <Badge variant="outline" className="text-[10px] tabular-nums">
            decay {item.decay_weight.toFixed(2)}
          </Badge>
        </div>
      </div>
      {expanded && item.text && (
        <div className="pl-6 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">
          {item.text}
          {item.text.length >= 600 && <span className="opacity-60"> …</span>}
        </div>
      )}
      {(item.author || item.published_at) && (
        <div className="pl-6 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          {item.author ? <span>{item.author}</span> : null}
          {item.author && item.published_at ? <span> · </span> : null}
          {item.published_at ? <span>{item.published_at}</span> : null}
        </div>
      )}
    </div>
  )
}
