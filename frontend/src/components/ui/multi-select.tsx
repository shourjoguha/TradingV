import * as React from 'react'
import { Check, ChevronDown, X } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from './popover'
import { cn } from '@/lib/utils'

export interface MultiSelectOption {
  value: string
  label?: string
}

interface MultiSelectProps {
  options: MultiSelectOption[]
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  searchPlaceholder?: string
  className?: string
  /** Cap on rendered chips inside the trigger before collapsing into "+N more". */
  maxChips?: number
}

// Multi-select with searchable list, neumorphic styling, and chip preview
// in the trigger. No external command/cmdk wrapper — keeps the primitive
// dependency-light and easy to skin further.
export function MultiSelect({
  options,
  value,
  onChange,
  placeholder = 'Select…',
  searchPlaceholder = 'Search…',
  className,
  maxChips = 4,
}: MultiSelectProps) {
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState('')
  const selectedSet = React.useMemo(() => new Set(value), [value])

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter(
      (o) =>
        o.value.toLowerCase().includes(q) ||
        (o.label?.toLowerCase().includes(q) ?? false),
    )
  }, [options, query])

  const toggle = (v: string) => {
    if (selectedSet.has(v)) onChange(value.filter((x) => x !== v))
    else onChange([...value, v])
  }

  const remove = (e: React.MouseEvent, v: string) => {
    e.stopPropagation()
    onChange(value.filter((x) => x !== v))
  }

  const visibleChips = value.slice(0, maxChips)
  const overflow = value.length - visibleChips.length

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'flex min-h-10 w-full items-center justify-between gap-2 rounded-2xl bg-background px-3 py-1.5 text-sm text-foreground',
            'shadow-inset-sm transition-shadow duration-200 ease-out',
            'focus:outline-none focus:shadow-inset focus:ring-2 focus:ring-violet focus:ring-offset-2 focus:ring-offset-background',
            className,
          )}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <div className="flex flex-wrap items-center gap-1 min-w-0 flex-1">
            {value.length === 0 && (
              <span className="text-muted-foreground">{placeholder}</span>
            )}
            {visibleChips.map((v) => (
              <span
                key={v}
                className="inline-flex items-center gap-1 rounded-lg bg-card px-2 py-0.5 font-mono text-xs shadow-extruded-sm"
              >
                {v}
                <span
                  role="button"
                  tabIndex={0}
                  aria-label={`Remove ${v}`}
                  onClick={(e) => remove(e, v)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') remove(e as any, v)
                  }}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </span>
              </span>
            ))}
            {overflow > 0 && (
              <span className="font-mono text-[10px] text-muted-foreground">
                +{overflow} more
              </span>
            )}
          </div>
          <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <div className="p-2 border-b border-muted-foreground/10">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={searchPlaceholder}
            className="w-full rounded-xl bg-background px-3 py-1.5 text-sm font-mono shadow-inset-sm focus:outline-none focus:shadow-inset focus:ring-1 focus:ring-violet/40"
          />
        </div>
        <div className="max-h-64 overflow-y-auto p-1">
          {filtered.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground italic">
              No matches
            </div>
          ) : (
            filtered.map((o) => {
              const checked = selectedSet.has(o.value)
              return (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => toggle(o.value)}
                  className={cn(
                    'flex w-full items-center justify-between gap-2 rounded-xl px-3 py-1.5 text-left text-sm font-mono',
                    'transition-shadow duration-150',
                    checked ? 'bg-background shadow-inset-sm' : 'hover:bg-background hover:shadow-inset-sm',
                  )}
                  aria-selected={checked}
                  role="option"
                >
                  <span>{o.value}</span>
                  <span className="flex items-center gap-2">
                    {o.label && o.label !== o.value && (
                      <span className="text-[10px] text-muted-foreground">{o.label}</span>
                    )}
                    {checked && <Check className="h-4 w-4 text-violet" />}
                  </span>
                </button>
              )
            })
          )}
        </div>
        {value.length > 0 && (
          <div className="flex items-center justify-between border-t border-muted-foreground/10 p-2">
            <span className="text-[10px] font-mono text-muted-foreground">
              {value.length} selected
            </span>
            <button
              type="button"
              onClick={() => onChange([])}
              className="text-[10px] font-mono text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
            >
              Clear
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
