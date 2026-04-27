import * as React from 'react'
import { cn } from '@/lib/utils'

// Neumorphic input. Inset shadow at rest; deeper inset + accent ring
// on focus. No border. Same surface as page.
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-10 w-full rounded-2xl bg-background px-4 py-2 text-sm text-foreground ' +
          'shadow-inset-sm transition-shadow duration-200 ease-out ' +
          'placeholder:text-[#A0AEC0] ' +
          'focus-visible:outline-none focus-visible:shadow-inset focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2 focus-visible:ring-offset-background ' +
          'file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground ' +
          'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'
