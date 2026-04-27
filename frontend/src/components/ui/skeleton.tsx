import { cn } from '@/lib/utils'

// Neumorphic skeleton: inset shadow conveys "missing pillow" — the
// space looks pressed in, waiting to be filled. Subtle pulse on
// background tone (not opacity) so it stays in the same colorspace.
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-2xl bg-background shadow-inset-sm',
        className,
      )}
      {...props}
    />
  )
}
