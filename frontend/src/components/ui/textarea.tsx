import * as React from 'react'
import { cn } from '@/lib/utils'

// Neumorphic textarea. Same physics as Input: inset at rest, deeper
// inset + accent ring on focus. Slightly larger min-height for body
// content (notes, dismissal reasons).
export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        'flex min-h-[80px] w-full rounded-2xl bg-background px-4 py-3 text-sm text-foreground ' +
          'shadow-inset-sm transition-shadow duration-200 ease-out ' +
          'placeholder:text-[#A0AEC0] ' +
          'focus-visible:outline-none focus-visible:shadow-inset focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2 focus-visible:ring-offset-background ' +
          'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  ),
)
Textarea.displayName = 'Textarea'
