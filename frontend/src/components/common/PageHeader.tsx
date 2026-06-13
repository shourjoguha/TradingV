import type { ReactNode } from 'react'
import { InfoBubble } from './InfoBubble'

interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Right-side controls (refresh, filters, primary CTA, etc.) */
  actions?: ReactNode
  /** Optional leading icon (left of the title). Phase 2: stronger hierarchy. */
  icon?: React.ComponentType<{ className?: string }>
  /** When true, the primary anchor bar + larger type are suppressed (nested headers). */
  tight?: boolean
  /**
   * When true (default 2026-05-17 density audit), the `description` is
   * rendered as an (i)-hover tooltip next to the title rather than as an
   * always-on subtitle. Pass `descriptionInline` if a caller specifically
   * needs the prose visible (rare — reach for it only when the operator
   * has to act on the description text, not just read it).
   */
  descriptionInline?: boolean
}

/**
 * Standard page header. Used at the top of every top-level page so the
 * type scale, weight, and right-control alignment stay consistent.
 *
 * 2026-05-17 density audit: `description` is now an (i)-tooltip by
 * default (was always-on subtitle prose). Reclaims ~28px below every
 * page H1; description still readable on hover. Pages that need the
 * subtitle inline can pass `descriptionInline`.
 */
export function PageHeader({
  title,
  description,
  actions,
  icon: Icon,
  tight,
  descriptionInline,
}: PageHeaderProps) {
  if (tight) {
    return (
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
            {title}
            {description && !descriptionInline && (
              <InfoBubble label="About this page" content={description} size={14} />
            )}
          </h2>
          {description && descriptionInline && (
            <p className="text-muted-foreground text-sm mt-1">{description}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
      </div>
    )
  }

  return (
    <div className="flex items-start justify-between flex-wrap gap-3">
      <div className="min-w-0 flex-1">
        <h2 className="relative font-display text-3xl font-extrabold tracking-tight pl-4 flex items-center gap-3">
          {/* 4px primary anchor bar — claims hierarchy over page-tab strip */}
          <span
            aria-hidden
            className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-full bg-primary"
          />
          {Icon && <Icon className="h-6 w-6 text-primary" />}
          {title}
          {description && !descriptionInline && (
            <InfoBubble label="About this page" content={description} size={16} />
          )}
        </h2>
        {description && descriptionInline && (
          <p className="text-muted-foreground text-sm mt-1 pl-4">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap shrink-0">{actions}</div>}
    </div>
  )
}
