import { useId, useState, type ReactNode } from 'react'

interface HoverTooltipProps {
  /** Trigger element. */
  children: ReactNode
  /** Content shown on hover/focus. */
  content: ReactNode
  /** Tooltip placement relative to the trigger. */
  side?: 'top' | 'bottom' | 'left' | 'right'
  /** Hard width on the popover. Default 240px keeps definitions readable. */
  width?: number
  className?: string
}

/**
 * One ephemeral tooltip pattern across the app. Replaces hand-rolled
 * `group-hover` tricks that varied in side/width/animation/aria. Works on
 * focus too (keyboard accessible).
 *
 * Use for short key/value or definition popovers. For richer content
 * (mini-charts, breakdowns) use HoverPopover instead.
 */
export function HoverTooltip({
  children,
  content,
  side = 'top',
  width = 240,
  className = '',
}: HoverTooltipProps) {
  const id = useId()
  const [open, setOpen] = useState(false)

  const sidePos: Record<string, string> = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  }

  return (
    <span
      className={`relative inline-flex align-middle ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span aria-describedby={open ? id : undefined}>{children}</span>
      {open && (
        <span
          id={id}
          role="tooltip"
          className={`absolute z-30 ${sidePos[side]} pointer-events-none`}
          style={{ width }}
        >
          <span className="block p-3 rounded-xl bg-card text-foreground shadow-extruded text-xs leading-relaxed text-left">
            {content}
          </span>
        </span>
      )}
    </span>
  )
}
