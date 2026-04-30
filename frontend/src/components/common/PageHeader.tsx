import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Right-side controls (refresh, filters, primary CTA, etc.) */
  actions?: ReactNode
}

/**
 * Standard page header. Used at the top of every top-level page so the
 * type scale, weight, and right-control alignment stay consistent.
 *
 * Replace ad-hoc `<div className="flex items-end justify-between">…</div>`
 * patterns across the app with `<PageHeader />`.
 */
export function PageHeader({ title, description, actions }: PageHeaderProps) {
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
