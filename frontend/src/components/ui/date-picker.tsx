import * as React from 'react'
import { format, parse } from 'date-fns'
import { CalendarIcon } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from './popover'
import { Calendar } from './calendar'
import { cn } from '@/lib/utils'

interface DatePickerProps {
  value: string                         // ISO YYYY-MM-DD; matches existing pages' state shape
  onChange: (next: string) => void
  className?: string
  placeholder?: string
  disabled?: (d: Date) => boolean
}

// ISO date string ↔ Date object helpers. Always treat the picker value as
// UTC midnight so the matrix's anchor-mode arithmetic stays timezone-stable
// (the rest of the predictions page parses YYYY-MM-DD as UTC too).
function isoToDate(iso: string): Date | undefined {
  if (!iso) return undefined
  const [y, m, d] = iso.split('-').map(Number)
  if (!y || !m || !d) return undefined
  return new Date(Date.UTC(y, m - 1, d))
}

function dateToIso(d: Date): string {
  // Use UTC to round-trip without DST drift.
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

export function DatePicker({
  value,
  onChange,
  className,
  placeholder = 'Pick a date',
  disabled,
}: DatePickerProps) {
  const [open, setOpen] = React.useState(false)
  const selected = isoToDate(value)
  const display = selected ? format(parse(value, 'yyyy-MM-dd', new Date()), 'dd MMM yyyy') : ''

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            // Mirrors Input + SelectTrigger styling so the field reads as
            // part of the same form palette.
            'flex h-10 w-full items-center justify-between rounded-2xl bg-background px-4 py-2 text-sm font-mono text-foreground',
            'shadow-inset-sm transition-shadow duration-200 ease-out',
            'focus:outline-none focus:shadow-inset focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background',
            !selected && 'text-muted-foreground',
            className,
          )}
        >
          <span>{display || placeholder}</span>
          <CalendarIcon className="h-4 w-4 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected}
          onSelect={(d) => {
            if (d) {
              // react-day-picker emits a local-time Date; reproject to UTC ISO.
              const utc = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
              onChange(dateToIso(utc))
              setOpen(false)
            }
          }}
          disabled={disabled}
        />
      </PopoverContent>
    </Popover>
  )
}
