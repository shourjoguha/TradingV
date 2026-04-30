import { Skeleton } from '../ui/skeleton'

/** Stack of N skeleton rows. Default 3. */
export function TableSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

/** Single rectangular skeleton sized for a card body. */
export function CardSkeleton({ className = 'h-24 w-full' }: { className?: string }) {
  return <Skeleton className={className} />
}

/** Tiny loading text — used inline, not as a panel. */
export function InlineLoading({ label = 'Loading…' }: { label?: string }) {
  return <span className="text-xs text-muted-foreground italic">{label}</span>
}
