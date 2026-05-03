import { ExternalLink } from 'lucide-react'
import type { EvidenceItem } from '../../lib/types'
import { Badge } from '../ui/badge'
import { AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion'

interface Props {
  item: EvidenceItem
  value: string
  vaultName?: string
}

function obsidianUri(vaultPath: string, vaultName: string): string {
  const file = vaultPath.replace(/\.md$/i, '')
  return `obsidian://open?vault=${encodeURIComponent(vaultName)}&file=${encodeURIComponent(file)}`
}

export function EvidenceItemRow({ item, value, vaultName = 'knowledge-vault' }: Props) {
  const uri = obsidianUri(item.vault_path, vaultName)
  const label = item.title || item.vault_path.split('/').pop() || item.vault_path

  return (
    <AccordionItem value={value}>
      <AccordionTrigger>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-xs text-foreground/90 truncate" title={label}>
            {label}
          </span>
          <div className="flex items-center gap-1.5 ml-auto tabular-nums shrink-0">
            <Badge variant="outline" className="text-[10px]">
              score {item.score.toFixed(3)}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              sim {item.similarity.toFixed(2)}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              decay {item.decay_weight.toFixed(2)}
            </Badge>
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-2 pt-1">
          <a
            href={uri}
            className="font-medium text-sm text-foreground hover:text-violet inline-flex items-center gap-1 break-all"
            title="Open in Obsidian"
          >
            {label}
            <ExternalLink className="h-3 w-3 shrink-0" />
          </a>
          <div className="text-[11px] font-mono text-muted-foreground break-all">
            {item.vault_path}
            {item.section ? ` › ${item.section}` : ''}
          </div>
          {item.text && (
            <div className="text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">
              {item.text}
              {item.text.length >= 600 && <span className="opacity-60"> …</span>}
            </div>
          )}
          {(item.author || item.published_at) && (
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              {item.author ? <span>{item.author}</span> : null}
              {item.author && item.published_at ? <span> · </span> : null}
              {item.published_at ? <span>{item.published_at}</span> : null}
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  )
}
