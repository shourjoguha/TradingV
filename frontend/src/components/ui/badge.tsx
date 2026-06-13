import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

// Neumorphic badges. Inset-sm shadow gives them a "stamped" feel that
// reads as a status indicator without competing with primary CTAs.
// Variants map to neumorphic-toned semantic palette (success/danger/
// warning) plus muted/primary for neutral and primary contexts.
const badgeVariants = cva(
  'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' +
    'shadow-inset-sm transition-colors ' +
    'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2',
  {
    variants: {
      variant: {
        default: 'bg-primary text-white',
        secondary: 'bg-background text-muted-foreground',
        destructive: 'bg-danger-bg text-danger-fg',
        success: 'bg-success-bg text-success-fg',
        warning: 'bg-warning-bg text-warning-fg',
        outline: 'bg-background text-foreground',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { badgeVariants }
