import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Neumorphic card. Same surface as page background; depth from the
 * extruded shadow. No border, no contrast bg.
 *
 * 2026-05-17 type/spacing recast:
 *   - CardHeader/Content/Footer: p-4 md:p-5 (was p-5 md:p-6). Tighter
 *     frame around denser type; ratio target 2:1 padding:gap.
 *   - CardTitle: text-base leading-snug (was text-lg leading-none).
 *     One canonical size for the role — kill the 14/16/18 muddle.
 *     leading-snug 1.375 so wrapped titles don't collide.
 *   - CardDescription: text-xs (was text-sm). Every callsite was already
 *     overriding to text-xs — finished the job + dropped the override.
 */
export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'rounded-3xl bg-background text-foreground shadow-extruded',
        className,
      )}
      {...props}
    />
  ),
)
Card.displayName = 'Card'

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    // 2026-05-17 density audit: bottom padding tightened to `pb-2` so the
    // gap between header text and the first row of content is 8px (was
    // 16/20px from full p-4/md:p-5). Cuts whitespace 50% w/o requiring
    // per-card `pb-N` overrides. Side padding still p-4 md:p-5.
    <div ref={ref} className={cn('flex flex-col space-y-2 p-4 md:p-5 pb-2 md:pb-2', className)} {...props} />
  ),
)
CardHeader.displayName = 'CardHeader'

export const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('font-display font-bold text-base leading-snug tracking-tight', className)} {...props} />
  ),
)
CardTitle.displayName = 'CardTitle'

export const CardDescription = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('text-xs text-muted-foreground', className)} {...props} />
  ),
)
CardDescription.displayName = 'CardDescription'

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn('p-4 md:p-5 pt-0', className)} {...props} />,
)
CardContent.displayName = 'CardContent'

export const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex items-center p-4 md:p-5 pt-0', className)} {...props} />
  ),
)
CardFooter.displayName = 'CardFooter'
