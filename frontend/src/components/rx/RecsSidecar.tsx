/**
 * RecsSidecar — right-rail context for /motion/recs.
 *
 * Tiles:
 *   - Funnel: open / snoozed / acted / dismissed (last 60d) — gives
 *     the operator a sense of disposition habits at a glance
 *   - Aging breakdown — how many recs are >14d old (aging) or have
 *     snooze_count ≥2 (forced)
 *   - Tip block — operator hint on running /rx-finance manually
 */
import { useRxRecs } from '../../hooks/use-api'
import { SidecarTile } from '../common/DetailSidecar'
import { Stethoscope } from 'lucide-react'

function pctStr(n: number, total: number): string {
  if (total === 0) return '—'
  return `${Math.round((n / total) * 100)}%`
}

export function RecsSidecar() {
  const { data } = useRxRecs({ window_days: 60, limit: 200 })
  const items = data?.items ?? []
  const total = items.length
  const counts = {
    open: items.filter((r) => r.status === 'open').length,
    snoozed: items.filter((r) => r.status === 'snoozed').length,
    acted: items.filter((r) => r.status === 'acted').length,
    dismissed: items.filter((r) => r.status === 'dismissed').length,
  }
  const aging = items.filter((r) => r.aging).length
  const forced = items.filter((r) => r.forced_decision).length

  return (
    <>
      <SidecarTile label="Disposition funnel (60d)">
        {total === 0 ? (
          <p className="text-xs text-muted-foreground">No recs yet.</p>
        ) : (
          <div className="space-y-2">
            <FunnelRow label="open" n={counts.open} total={total} color="bg-yellow-500/60" />
            <FunnelRow label="snoozed" n={counts.snoozed} total={total} color="bg-blue-500/60" />
            <FunnelRow label="acted" n={counts.acted} total={total} color="bg-green-500/60" />
            <FunnelRow label="dismissed" n={counts.dismissed} total={total} color="bg-muted-foreground/40" />
            <div className="pt-1 mt-1 border-t border-border/30 text-xs text-muted-foreground">
              act rate {pctStr(counts.acted, total)} · skip rate {pctStr(counts.dismissed, total)}
            </div>
          </div>
        )}
      </SidecarTile>

      <SidecarTile label="Attention flags">
        <div className="space-y-2 text-sm">
          <Row label="Aging (>14d open)" value={aging} tone={aging > 0 ? 'amber' : 'muted'} />
          <Row label="Forced (≥2 snoozes)" value={forced} tone={forced > 0 ? 'red' : 'muted'} />
        </div>
      </SidecarTile>

      <SidecarTile label="Next batch">
        <p className="text-xs text-muted-foreground">
          Generator is operator-triggered. Run <code className="text-[11px]">/rx-finance</code> in
          Claude Code on the laptop to ingest a new rec.
        </p>
      </SidecarTile>
    </>
  )
}

function FunnelRow({
  label,
  n,
  total,
  color,
}: { label: string; n: number; total: number; color: string }) {
  const pct = total === 0 ? 0 : (n / total) * 100
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs mb-0.5">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums">{n}</span>
      </div>
      <div className="h-1 rounded-full bg-muted overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function Row({ label, value, tone }: { label: string; value: number; tone: 'amber' | 'red' | 'muted' }) {
  const valColor =
    tone === 'amber' ? 'text-amber-700' :
    tone === 'red' ? 'text-red-700' :
    'text-muted-foreground'
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={`text-base font-display font-bold tabular-nums ${valColor}`}>{value}</span>
    </div>
  )
}
