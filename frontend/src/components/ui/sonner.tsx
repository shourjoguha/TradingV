import { Toaster as Sonner } from 'sonner'

type ToasterProps = React.ComponentProps<typeof Sonner>

// Sonner has limited theming; we style via classNames. The toast
// becomes an extruded card that floats above the page. Action
// button is accent violet. Less integrated than handwritten
// neumorphic primitives but acceptable trade.
export function Toaster({ ...props }: ToasterProps) {
  return (
    <Sonner
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            'group toast rounded-2xl bg-background text-foreground shadow-extruded',
          description: 'text-muted-foreground',
          actionButton:
            'rounded-xl bg-violet text-white shadow-extruded-sm',
          cancelButton:
            'rounded-xl bg-background text-muted-foreground shadow-inset-sm',
          success: 'text-success',
          error: 'text-danger',
        },
      }}
      {...props}
    />
  )
}
