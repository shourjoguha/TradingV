/**
 * StatusBadge — unified vocabulary across recs / hypotheses / trades / opportunities / positions.
 *
 * Replaces three drifted dialects:
 *   - pages/RxFinance.tsx::statusBadge() — raw tailwind colors
 *   - pages/Theses.tsx — semantic tokens, ad-hoc
 *   - pages/Trades.tsx — Badge variant on side (semantic miscoding)
 *
 * Convention:
 *   live / awaiting       → warning  (yellow/amber)  — operator should look
 *   active / on-track     → success  (teal)          — no action needed
 *   resolved positive     → success solid            — done well
 *   resolved neutral      → muted    (gray)          — skipped / cancelled
 *   resolved negative     → danger   (coral)         — broke / invalidated
 *   system-touched        → violet outline           — auto-revived / auto-promoted
 *   snoozed / deferred    → blue                     — operator chose to wait
 *   flag — aging          → amber outline
 *   flag — forced         → coral outline
 *
 * API:
 *   <StatusBadge kind="rec" value="open" />
 *   <StatusBadge kind="hypothesis" value="active" />
 *   <StatusBadge kind="trade" value="open" />
 *   <StatusBadge kind="flag" value="forced" />
 */
import { AlertTriangle, Clock } from 'lucide-react'
import { Badge } from '../ui/badge'

export type StatusKind =
  | 'rec'
  | 'hypothesis'
  | 'trade'
  | 'opportunity'
  | 'position'
  | 'flag'

// Token classes — every shape goes through these so we never reintroduce drift.
const TONE_CLASSES: Record<string, string> = {
  warning:        'bg-yellow-500/15 text-yellow-700 border-yellow-500/30',
  warningStrong:  'bg-amber-500/20 text-amber-800 border-amber-500/60 font-semibold',
  warningOutline: 'border-amber-500/60 text-amber-700 bg-transparent',
  success:        'bg-green-500/15 text-green-700 border-green-500/30',
  successOutline: 'border-green-500/40 text-green-700 bg-transparent',
  successStrong:  'bg-green-500/25 text-green-800 border-green-500/60 font-semibold',
  danger:         'bg-red-500/15 text-red-700 border-red-500/30',
  dangerOutline:  'border-red-600 text-red-700 bg-red-500/10',
  muted:          'bg-muted text-muted-foreground border-transparent',
  info:           'bg-blue-500/15 text-blue-700 border-blue-500/30',
  systemOutline:  'border-violet/40 text-violet bg-transparent',
}

interface StatusMap {
  label: string
  tone: keyof typeof TONE_CLASSES
  icon?: React.ComponentType<{ className?: string }>
}

const REC_STATUS: Record<string, StatusMap> = {
  open:                        { label: 'open',         tone: 'warning' },
  snoozed:                     { label: 'snoozed',      tone: 'info' },
  auto_revived:                { label: 'auto-revived', tone: 'warningStrong' },
  acted:                       { label: 'acted',        tone: 'success' },
  dismissed:                   { label: 'dismissed',    tone: 'muted' },
}

const HYP_STATUS: Record<string, StatusMap> = {
  active:        { label: 'active',        tone: 'success' },
  expired:       { label: 'expired',       tone: 'muted' },
  invalidated:   { label: 'invalidated',   tone: 'danger' },
  cancelled:     { label: 'cancelled',     tone: 'muted' },
  manual_closed: { label: 'manual closed', tone: 'muted' },
}

const TRADE_STATUS: Record<string, StatusMap> = {
  open:   { label: 'open',   tone: 'warning' },
  closed: { label: 'closed', tone: 'success' },
}

const OPP_STATUS: Record<string, StatusMap> = {
  fresh:     { label: 'fresh',     tone: 'warning' },
  acted:     { label: 'acted',     tone: 'success' },
  dismissed: { label: 'dismissed', tone: 'muted' },
  expired:   { label: 'expired',   tone: 'muted' },
}

const POSITION_STATUS: Record<string, StatusMap> = {
  healthy:      { label: 'healthy',      tone: 'success' },
  concentrated: { label: 'concentrated', tone: 'warningOutline', icon: AlertTriangle },
}

const FLAG_STATUS: Record<string, StatusMap> = {
  aging:   { label: 'aging',    tone: 'warningOutline', icon: Clock },
  forced:  { label: 'forced',   tone: 'dangerOutline',  icon: AlertTriangle },
  revived: { label: 'revived',  tone: 'warningStrong' },
  rec:     { label: 'rec',      tone: 'info' },
  conflict:{ label: 'conflict', tone: 'dangerOutline',  icon: AlertTriangle },
}

const REGISTRY: Record<StatusKind, Record<string, StatusMap>> = {
  rec:         REC_STATUS,
  hypothesis:  HYP_STATUS,
  trade:       TRADE_STATUS,
  opportunity: OPP_STATUS,
  position:    POSITION_STATUS,
  flag:        FLAG_STATUS,
}

export function StatusBadge({
  kind,
  value,
  size = 'sm',
}: {
  kind: StatusKind
  value: string
  size?: 'xs' | 'sm'
}) {
  const map = REGISTRY[kind]?.[value]
  if (!map) {
    // Unknown values fall back to a muted label so we never crash on a
    // backend change that adds a new status.
    return <Badge variant="outline" className={TONE_CLASSES.muted}>{value}</Badge>
  }
  const Icon = map.icon
  const sizeClass = size === 'xs' ? 'text-[10px] py-0 px-2' : 'text-xs'
  return (
    <Badge
      variant="outline"
      className={[TONE_CLASSES[map.tone], sizeClass, 'inline-flex items-center gap-1'].join(' ')}
    >
      {Icon && <Icon className="h-3 w-3" />}
      {map.label}
    </Badge>
  )
}
