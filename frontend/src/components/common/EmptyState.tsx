import type { ComponentType, ReactNode } from 'react'
import type { LucideProps } from 'lucide-react'

interface EmptyStateProps {
  icon?: ComponentType<LucideProps>
  title: ReactNode
  description?: ReactNode
  /** Optional action — usually a primary button. */
  action?: ReactNode
  /** When the parent already provides a card/inset, set true to drop the
   * inset shadow and let the parent's chrome carry the visual weight. */
  bare?: boolean
}

/**
 * One-shape empty state across the app. Replaces hand-rolled "No data"
 * divs that used to vary in margin / icon size / color / wording cadence.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  bare = false,
}: EmptyStateProps) {
  const wrapper = bare
    ? 'text-center py-8 flex flex-col items-center'
    : 'text-center py-12 text-sm rounded-2xl shadow-inset-sm bg-background flex flex-col items-center'
  return (
    <div className={wrapper}>
      {Icon && <Icon className="h-8 w-8 mb-2 text-muted-foreground/50" />}
      <p className="text-sm text-foreground font-medium">{title}</p>
      {description && (
        <p className="text-xs text-muted-foreground mt-1 max-w-md">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
