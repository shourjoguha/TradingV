/**
 * DetailSidecar — right-rail context strip for list/table pages.
 *
 * Visual designer P0-3: "every list/table page has ~600px of empty grey
 * clay below the table. Fill it with contextual data." This primitive
 * provides the canonical 2-column page-shell so list pages get a
 * narrative sidebar without each page reinventing the layout.
 *
 * Layout (≥md):
 *   ┌─────────────────────────────────┬─────────────┐
 *   │  main content (≥920px, flex-1)  │  sidecar    │
 *   │                                 │  (320–360px) │
 *   └─────────────────────────────────┴─────────────┘
 * Below md: stacked.
 *
 * Sidecar children are typically StatTile / SparklineTile / textual
 * context. The container provides the spacing; consumers control the
 * exact tiles per page.
 */
import { ReactNode } from 'react'

export function PageWithSidecar({
  main,
  sidecar,
  sidecarWidth = 'w-80',
}: {
  main: ReactNode
  sidecar: ReactNode
  sidecarWidth?: 'w-72' | 'w-80' | 'w-96'
}) {
  return (
    <div className="flex flex-col xl:flex-row gap-4 items-start">
      <div className="flex-1 min-w-0 w-full">{main}</div>
      <aside className={`${sidecarWidth} shrink-0 space-y-3 w-full xl:w-auto`}>
        {sidecar}
      </aside>
    </div>
  )
}

/**
 * SidecarTile — compact card for sidecar widgets.
 * Inset by default (ambient, not primary attention).
 */
export function SidecarTile({
  label,
  children,
  className = '',
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`rounded-2xl bg-background shadow-inset-sm p-4 ${className}`}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
        {label}
      </div>
      {children}
    </div>
  )
}
