import * as React from 'react'
import * as TogglePrimitive from '@radix-ui/react-toggle'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

// Neumorphic toggle. Off = extruded-sm pillow (ready to press).
// On (data-[state=on]) = inset (pressed-in well + accent text).
export const toggleVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-xl text-sm font-medium ' +
    'transition-all duration-200 ease-out ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2 focus-visible:ring-offset-background ' +
    'disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default:
          'bg-background text-muted-foreground shadow-extruded-sm ' +
          'hover:text-foreground ' +
          'data-[state=on]:shadow-inset-sm data-[state=on]:text-violet',
        outline:
          'bg-background text-muted-foreground shadow-extruded-sm ' +
          'hover:text-foreground ' +
          'data-[state=on]:shadow-inset data-[state=on]:text-violet',
      },
      size: {
        default: 'h-9 px-3 min-w-9',
        sm: 'h-7 px-2 min-w-7 text-xs',
        lg: 'h-10 px-4 min-w-10',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export const Toggle = React.forwardRef<
  React.ElementRef<typeof TogglePrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof TogglePrimitive.Root> & VariantProps<typeof toggleVariants>
>(({ className, variant, size, ...props }, ref) => (
  <TogglePrimitive.Root ref={ref} className={cn(toggleVariants({ variant, size, className }))} {...props} />
))
Toggle.displayName = TogglePrimitive.Root.displayName
