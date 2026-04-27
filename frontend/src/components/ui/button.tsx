import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

// Neumorphic button. Default = extruded surface matching page; primary
// = accent-violet pillow with white text. Hover lifts 1px + deepens
// shadow; active presses 0.5px + flips to inset.
const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-2xl text-sm font-medium ' +
    'transition-all duration-200 ease-out ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2 focus-visible:ring-offset-background ' +
    'disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default:
          'bg-background text-foreground shadow-extruded-sm ' +
          'hover:-translate-y-[1px] hover:shadow-extruded ' +
          'active:translate-y-[0.5px] active:shadow-inset-sm',
        primary:
          'bg-violet text-white shadow-extruded-sm ' +
          'hover:-translate-y-[1px] hover:bg-violet-light hover:shadow-extruded ' +
          'active:translate-y-[0.5px] active:shadow-inset-sm',
        destructive:
          'bg-danger text-white shadow-extruded-sm ' +
          'hover:-translate-y-[1px] hover:shadow-extruded ' +
          'active:translate-y-[0.5px] active:shadow-inset-sm',
        outline:
          'bg-background text-foreground shadow-extruded-sm ' +
          'hover:-translate-y-[1px] hover:shadow-extruded hover:text-violet ' +
          'active:translate-y-[0.5px] active:shadow-inset-sm',
        secondary:
          'bg-background text-muted-foreground shadow-extruded-sm ' +
          'hover:text-foreground hover:shadow-extruded ' +
          'active:shadow-inset-sm',
        ghost:
          'bg-transparent text-muted-foreground hover:text-violet ' +
          'hover:shadow-inset-sm active:shadow-inset',
        link: 'text-violet underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-5 py-2',
        sm: 'h-8 px-3 text-xs rounded-xl',
        lg: 'h-12 px-8 text-base',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  },
)
Button.displayName = 'Button'

export { buttonVariants }
