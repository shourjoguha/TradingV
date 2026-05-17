import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Right-side controls (refresh, filters, primary CTA, etc.) */
  actions?: ReactNode
  /** Optional leading icon (left of the title). Phase 2: stronger hierarchy. */
  icon?: React.ComponentType<{ className?: string }>
  /** When true, the violet anchor bar + larger type are suppressed (nested headers). */
  tight?: boolean
}

/**
 * Standard page header. Used at the top of every top-level page so the
 * type scale, weight, and right-control alignment stay consistent.
 *
 * Phase 2 (2026-05-17): added violet anchor bar + larger H1 (3xl/extrabold)
 * per visual designer P0-2 to disambiguate from page-tab strip.
 *
 * Backwards-compatible: existing callers without `icon`/`tight` look the
 * same except for the slightly larger/heavier H1 and the 4px violet bar.
 */
export function PageHeader({ title, description, actions, icon: Icon, tight }: PageHeaderProps) {
  if (tight) {
    return (
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">{title}</h2>
          {description && (
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
          {/* 4px violet anchor bar — claims hierarchy over page-tab strip */}
          <span
            aria-hidden
            className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-full bg-violet"
          />
          {Icon && <Icon className="h-6 w-6 text-violet" />}
          {title}
        </h2>
        {description && (
          <p className="text-muted-foreground text-sm mt-1 pl-4">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap shrink-0">{actions}</div>}
    </div>
  )
}
