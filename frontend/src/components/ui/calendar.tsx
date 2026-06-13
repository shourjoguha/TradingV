import * as React from 'react'
import { DayPicker } from 'react-day-picker'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

export type CalendarProps = React.ComponentProps<typeof DayPicker>

// Neumorphic skin for react-day-picker. Selected day uses the primary
// accent (extruded); today gets a subtle inset ring; nav buttons read
// like the rest of the soft-UI button palette.
export function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: CalendarProps) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn('p-3', className)}
      classNames={{
        months: 'flex flex-col sm:flex-row gap-4',
        month: 'space-y-3',
        month_caption: 'flex justify-center pt-1 relative items-center',
        caption_label: 'text-sm font-medium text-foreground',
        nav: 'flex items-center gap-1',
        button_previous: cn(
          'absolute left-1 top-1 inline-flex h-7 w-7 items-center justify-center rounded-xl',
          'bg-background shadow-inset-sm hover:shadow-extruded-sm transition-shadow',
          'text-muted-foreground hover:text-foreground',
        ),
        button_next: cn(
          'absolute right-1 top-1 inline-flex h-7 w-7 items-center justify-center rounded-xl',
          'bg-background shadow-inset-sm hover:shadow-extruded-sm transition-shadow',
          'text-muted-foreground hover:text-foreground',
        ),
        month_grid: 'w-full border-collapse',
        weekdays: 'flex',
        weekday:
          'w-9 text-xs font-medium text-muted-foreground',
        week: 'flex w-full mt-1',
        day: cn(
          'relative p-0 text-center text-sm',
          'h-9 w-9 [&:has([aria-selected])]:bg-transparent',
        ),
        day_button: cn(
          'inline-flex h-9 w-9 items-center justify-center rounded-xl font-mono text-sm',
          'transition-shadow duration-150',
          'hover:bg-background hover:shadow-inset-sm',
          'focus:outline-none focus:shadow-inset focus:ring-2 focus:ring-primary/40',
        ),
        selected: cn(
          '[&>button]:bg-primary [&>button]:text-white',
          '[&>button]:shadow-extruded-sm [&>button:hover]:shadow-extruded',
          '[&>button:hover]:bg-primary [&>button:hover]:text-white',
        ),
        today: '[&>button]:ring-2 [&>button]:ring-primary/40 [&>button]:ring-offset-1',
        outside: '[&>button]:text-muted-foreground/40',
        disabled: '[&>button]:opacity-30 [&>button]:cursor-not-allowed',
        hidden: 'invisible',
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation, ...rest }) =>
          orientation === 'left' ? (
            <ChevronLeft className="h-4 w-4" {...rest} />
          ) : (
            <ChevronRight className="h-4 w-4" {...rest} />
          ),
      }}
      {...props}
    />
  )
}
