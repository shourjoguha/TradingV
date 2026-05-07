import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BookOpen } from 'lucide-react'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '../ui/accordion'
import { Badge } from '../ui/badge'
import type { SourceContextItem } from '../../lib/types'

interface Props {
  items: SourceContextItem[]
}

/**
 * Operator-authored `_index.md` vignettes, prepended to the research bundle
 * for every query whose evidence falls under the same folder tree. Verbatim —
 * no token cap.
 */
export function SourceContextSection({ items }: Props) {
  if (!items.length) return null

  return (
    <div className="space-y-1.5">
      <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
        <BookOpen className="h-3 w-3" />
        Source context ({items.length})
      </div>
      <Accordion type="multiple" className="space-y-1.5">
        {items.map((item, i) => (
          <AccordionItem
            key={`${item.path}-${i}`}
            value={`sc-${i}`}
          >
            <AccordionTrigger>
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <span className="text-xs text-foreground/90 truncate" title={item.title || item.path}>
                  {item.title || item.path}
                </span>
                <Badge variant="outline" className="text-[10px] font-mono ml-auto shrink-0">
                  {item.applies_to.length} ev
                </Badge>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-2 pt-1">
                <div className="text-[11px] font-mono text-muted-foreground break-all">
                  {item.path}
                </div>
                <div className="prose prose-sm max-w-none text-foreground/90 leading-relaxed">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {item.body}
                  </ReactMarkdown>
                </div>
                {item.applies_to.length > 0 && (
                  <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                    applies to {item.applies_to.length} evidence path
                    {item.applies_to.length === 1 ? '' : 's'}
                  </div>
                )}
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  )
}
