import { Link } from 'react-router-dom'
import { Info } from 'lucide-react'
import { HoverTooltip } from './HoverTooltip'
import { getGlossary } from '../../lib/glossary'

interface InfoBubbleProps {
  /** Glossary term key (see frontend/src/lib/glossary.ts). */
  term: string
  /** Override placement when the trigger is near a viewport edge. */
  side?: 'top' | 'bottom' | 'left' | 'right'
  /** Pixel size of the (i) circle. Default 12 (matches text-xs leading). */
  size?: number
}

/**
 * Hoverable (i) circle. Renders the glossary's `long` definition and a
 * "Read more" link to the corresponding /docs/metrics anchor when one
 * exists. Drop next to any data label that has a glossary entry.
 *
 * Renders nothing if the term key isn't registered — encourages explicit
 * registry hits rather than ad-hoc tooltip text scattered across pages.
 */
export function InfoBubble({ term, side = 'top', size = 12 }: InfoBubbleProps) {
  const entry = getGlossary(term)
  if (!entry) return null

  return (
    <HoverTooltip
      side={side}
      width={320}
      content={
        <div className="space-y-2">
          <div className="font-semibold">{entry.short}</div>
          <div className="text-muted-foreground">{entry.long}</div>
          {entry.directional && (
            <div className="space-y-1 pt-1.5 border-t border-muted-foreground/15">
              <div className="flex gap-1.5">
                <span className="text-success font-mono text-[10px] mt-0.5 shrink-0">▲</span>
                <span><span className="font-medium">Up:</span> {entry.directional.up}</span>
              </div>
              <div className="flex gap-1.5">
                <span className="text-danger font-mono text-[10px] mt-0.5 shrink-0">▼</span>
                <span><span className="font-medium">Down:</span> {entry.directional.down}</span>
              </div>
              {entry.directional.threshold && (
                <div className="flex gap-1.5">
                  <span className="text-warning font-mono text-[10px] mt-0.5 shrink-0">⚑</span>
                  <span><span className="font-medium">Watch:</span> {entry.directional.threshold}</span>
                </div>
              )}
            </div>
          )}
          {entry.docHref && (
            <Link
              to={entry.docHref}
              className="inline-block mt-1 text-violet hover:underline"
            >
              Read more →
            </Link>
          )}
        </div>
      }
    >
      <button
        type="button"
        aria-label={`Definition: ${entry.short}`}
        className="inline-flex items-center justify-center text-muted-foreground/70 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:text-foreground"
        style={{ width: size + 4, height: size + 4 }}
      >
        <Info style={{ width: size, height: size }} />
      </button>
    </HoverTooltip>
  )
}
