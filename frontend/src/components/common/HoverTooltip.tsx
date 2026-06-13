import { useId, useRef, useState, type ReactNode } from 'react'

interface HoverTooltipProps {
  /** Trigger element. */
  children: ReactNode
  /** Content shown on hover/focus. */
  content: ReactNode
  /** Preferred placement relative to the trigger. May be flipped to the
   *  opposite side at open-time if the viewport edge would clip it. */
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
 * Hover-stable: the popover stays open while the mouse moves from trigger
 * onto the popover itself, so links inside ("Read more") are clickable.
 *
 * Auto-flip (2026-05-17): the requested `side` is the *preferred* side.
 * On open, getBoundingClientRect on the trigger checks whether the
 * tooltip would be clipped by the viewport (e.g. top-anchored tooltip
 * on a page-header icon — gets hidden behind the browser's address
 * bar). If insufficient room, flip to the opposite side. Re-measures
 * on every open so scroll/resize between opens doesn't strand a side.
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
  const [effectiveSide, setEffectiveSide] = useState<typeof side>(side)
  const triggerRef = useRef<HTMLSpanElement>(null)
  // Brief close-delay so moving the cursor from trigger → popover doesn't
  // collapse it. The popover's own onMouseEnter cancels the timer.
  const closeTimer = useRef<number | null>(null)

  const openNow = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
    // Re-measure on each open so scroll/resize between opens picks the
    // right side. Conservative tooltip-height estimate of 200px covers
    // most definition payloads; over-flips on tall directional bodies
    // are preferable to under-flips (which clip).
    const el = triggerRef.current
    let next: typeof side = side
    if (el) {
      const rect = el.getBoundingClientRect()
      const vw = window.innerWidth
      const vh = window.innerHeight
      const margin = 16
      const estHeight = 200
      const estWidth = width + 16
      if (side === 'top' && rect.top < estHeight + margin) next = 'bottom'
      else if (side === 'bottom' && vh - rect.bottom < estHeight + margin) next = 'top'
      else if (side === 'left' && rect.left < estWidth) next = 'right'
      else if (side === 'right' && vw - rect.right < estWidth) next = 'left'
    }
    setEffectiveSide(next)
    setOpen(true)
  }
  const scheduleClose = () => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current)
    closeTimer.current = window.setTimeout(() => {
      setOpen(false)
      closeTimer.current = null
    }, 120)
  }

  const sidePos: Record<string, string> = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  }

  return (
    <span
      ref={triggerRef}
      className={`relative inline-flex align-middle ${className}`}
      onMouseEnter={openNow}
      onMouseLeave={scheduleClose}
      onFocus={openNow}
      onBlur={scheduleClose}
    >
      <span aria-describedby={open ? id : undefined}>{children}</span>
      {open && (
        <span
          id={id}
          role="tooltip"
          className={`absolute z-50 ${sidePos[effectiveSide]}`}
          style={{ width }}
          onMouseEnter={openNow}
          onMouseLeave={scheduleClose}
        >
          <span className="block p-3 rounded-xl bg-card text-foreground shadow-extruded text-xs leading-relaxed text-left whitespace-normal break-words">
            {content}
          </span>
        </span>
      )}
    </span>
  )
}
