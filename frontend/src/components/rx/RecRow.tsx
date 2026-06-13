/**
 * RecRow — single rec list row, mobile-stacked card variant.
 *
 * Operator on phone: 7-column table side-scrolls into oblivion (UX
 * strategist B5). This card renders the same signal in a vertical
 * stack so flags + status are visible without horizontal scroll.
 *
 * Phase 5 — used in the responsive rec list (table for ≥md, stack for <md).
 */
import { Link } from 'react-router-dom'
import type { RxRecListItem } from '../../hooks/use-api'
import { DriftBar } from '../charts/svg/DriftBar'
import { StatusBadge } from '../common/StatusBadge'

/**
 * Pre-attentive disposition rail (2026-05-17 color taxonomy). 2px left bar
 * per rec row keyed to status — operator scans the bar color before
 * reading the badge. Shared by RecCard (mobile) and the desktop table in
 * pages/RxFinance.tsx.
 *
 *   primary  = open    (still needs decision — primary action color)
 *   steel   = snoozed (sleeping, low-attention)
 *   growth  = acted   (committed; matches closed-trade win)
 *   muted   = dismissed (filed away, no further action)
 */
export const RX_STATUS_BAR_BG: Record<string, string> = {
  open:         'bg-primary',
  snoozed:      'bg-identity-ambient',
  auto_revived: 'bg-identity-ambient',
  acted:        'bg-identity-growth',
  dismissed:    'bg-muted-foreground/40',
}

function relTime(iso: string): string {
  const now = Date.now()
  const t = new Date(iso).getTime()
  const ago = Math.max(0, now - t)
  const min = Math.floor(ago / 60_000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const d = Math.floor(hr / 24)
  return `${d}d ago`
}

function recStatusValue(it: RxRecListItem): string {
  if (it.status === 'snoozed' && it.auto_revived) return 'auto_revived'
  return it.status
}

export interface RecRowAnnotations {
  /** Ticker the rec is about (best-effort extracted from tldr). */
  ticker?: string | null
  /** True when ticker is held in an open position. */
  inPosition?: boolean
  /** True when ticker is on the operator's watchlist. */
  inWatchlist?: boolean
  /** True when rec direction (trim/sell) conflicts with an open long, etc. */
  conflict?: boolean
}

export function RecCard({ rec, annot }: { rec: RxRecListItem; annot?: RecRowAnnotations }) {
  const barClass = RX_STATUS_BAR_BG[recStatusValue(rec)] ?? 'bg-muted-foreground/30'
  return (
    <Link
      to={`/motion/recs/${rec.id}`}
      className="relative block rounded-2xl bg-background shadow-inset-sm p-4 pl-5 hover:shadow-extruded-sm transition-all space-y-2"
    >
      <div
        aria-hidden
        className={`absolute left-0 top-2 bottom-2 w-[3px] rounded-r ${barClass}`}
      />
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-muted-foreground">{rec.short_id}</span>
        <span className="text-xs text-muted-foreground tabular-nums">{relTime(rec.created_at)}</span>
      </div>
      {rec.tldr_short && (
        <p className="text-sm leading-snug">{rec.tldr_short}</p>
      )}
      <div className="flex items-center gap-3">
        <DriftBar score={rec.drift_score} size="sm" />
        <span className="text-xs text-muted-foreground tabular-nums">conf {rec.confidence ?? '—'}</span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <StatusBadge kind="rec" value={recStatusValue(rec)} size="xs" />
        {rec.aging && <StatusBadge kind="flag" value="aging" size="xs" />}
        {rec.forced_decision && <StatusBadge kind="flag" value="forced" size="xs" />}
        {annot?.conflict && <StatusBadge kind="flag" value="conflict" size="xs" />}
        {annot?.inPosition && (
          <span className="text-xs font-semibold text-primary">
            in position
          </span>
        )}
        {annot?.inWatchlist && !annot?.inPosition && (
          <span className="text-xs text-muted-foreground">
            on watchlist
          </span>
        )}
      </div>
    </Link>
  )
}
