import { Link } from 'react-router-dom'
import { Info } from 'lucide-react'
import { type ReactNode } from 'react'
import { HoverTooltip } from './HoverTooltip'
import { getGlossary } from '../../lib/glossary'

interface InfoBubbleProps {
  /** Glossary term key (see frontend/src/lib/glossary.ts). Optional when
   *  `content` is provided directly. */
  term?: string
  /** Ad-hoc tooltip content for one-off helper text that doesn't
   *  warrant a glossary entry (e.g. CardDescription promoted from
   *  always-on body to (i)-hover per the 2026-05-17 density audit). */
  content?: ReactNode
  /** Short headline used as the aria-label when `content` is given. */
  label?: string
  /** Override placement when the trigger is near a viewport edge. */
  side?: 'top' | 'bottom' | 'left' | 'right'
  /** Pixel size of the (i) circle. Default 12 (matches text-xs leading). */
  size?: number
}

/**
 * Hoverable (i) circle. Two modes:
 *   - `term` → renders the glossary entry (short / long / directional /
 *     docHref). Renders nothing if the key isn't registered.
 *   - `content` → renders the given ReactNode as tooltip body. Use for
 *     one-off explanatory copy that was previously always-on (e.g. the
 *     Today 4-up card descriptions promoted per density audit).
 *
 * One of `term` or `content` must be set. `term` wins if both are given.
 */
export function InfoBubble({ term, content, label, side = 'top', size = 12 }: InfoBubbleProps) {
  if (term) {
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
                  <span className="text-success font-mono text-xs mt-0.5 shrink-0">▲</span>
                  <span><span className="font-medium">Up:</span> {entry.directional.up}</span>
                </div>
                <div className="flex gap-1.5">
                  <span className="text-danger font-mono text-xs mt-0.5 shrink-0">▼</span>
                  <span><span className="font-medium">Down:</span> {entry.directional.down}</span>
                </div>
                {entry.directional.threshold && (
                  <div className="flex gap-1.5">
                    <span className="text-warning font-mono text-xs mt-0.5 shrink-0">⚑</span>
                    <span><span className="font-medium">Watch:</span> {entry.directional.threshold}</span>
                  </div>
                )}
              </div>
            )}
            {entry.docHref && (
              <Link
                to={entry.docHref}
                className="inline-block mt-1 text-primary hover:underline"
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

  if (!content) return null
  // Mirror the `term` variant's structure (2026-05-17 tooltip unification
  // — operator audit flagged inconsistent fonts/spacing across the two
  // call modes). Same width, same wrapping `space-y-2`, optional bold
  // `label` as the title row to match `entry.short`, then the body in
  // muted-foreground prose.
  return (
    <HoverTooltip
      side={side}
      width={320}
      content={
        <div className="space-y-2">
          {label && <div className="font-semibold">{label}</div>}
          <div className="text-muted-foreground">{content}</div>
        </div>
      }
    >
      <button
        type="button"
        aria-label={label ?? 'More info'}
        className="inline-flex items-center justify-center text-muted-foreground/70 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:text-foreground"
        style={{ width: size + 4, height: size + 4 }}
      >
        <Info style={{ width: size, height: size }} />
      </button>
    </HoverTooltip>
  )
}
