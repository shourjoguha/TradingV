/**
 * SectorLadderCard — single sector cell in the compact 3-col Sectors grid.
 *
 * 2026-05-17 follow-up: compressed from a full-width horizontal ladder
 * row to a stacked grid cell. Math preserved (rank · RS-indexed · 14-day
 * momentum chevron · z-score sparkline) but laid out in a card the
 * width of one of three columns — operator wanted "color-coded one-line
 * cards view from earlier" w/ the new metrics. Identity left-bar carries
 * sector identity color; tone of the RS-indexed value carries
 * direction-of-state (green if leading SPY, red if lagging).
 */
import type { MacroPoint } from '../../lib/types'
import type { MomentumDir } from '../../lib/sector-strength'
import { Sparkline } from '../charts/svg/Sparkline'
import { SECTOR_IDENTITY_BG } from '../../lib/macro-views'

interface SectorLadderCardProps {
  symbol: string
  label: string
  /** 1 = strongest RS vs SPY; null = insufficient history (renders "—"). */
  rank: number | null
  /** Z-scored series feeding the per-card sparkline. */
  zScoreSeries: MacroPoint[]
  /** 14-day RS momentum direction (drives the chevron + tone). */
  momentum: MomentumDir
  /** Raw RS-indexed value (renders as "+3.2%" / "−7.1%" vs SPY 1y). */
  rsIndexed: number | null
  selected: boolean
  onSelect: () => void
}

function ChevronGlyph({ dir }: { dir: MomentumDir }) {
  const color =
    dir === 'up'
      ? 'text-success-fg'
      : dir === 'down'
        ? 'text-danger-fg'
        : 'text-muted-foreground'
  const glyph = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '→'
  return (
    <span
      className={`text-xs font-mono leading-none ${color}`}
      aria-label={`momentum ${dir}`}
    >
      {glyph}
    </span>
  )
}

function fmtRsIndexed(v: number | null): string {
  if (v == null) return '—'
  const delta = v - 100
  const sign = delta >= 0 ? '+' : ''
  return `${sign}${delta.toFixed(1)}%`
}

export function SectorLadderCard({
  symbol,
  label,
  rank,
  zScoreSeries,
  momentum,
  rsIndexed,
  selected,
  onSelect,
}: SectorLadderCardProps) {
  const barClass = SECTOR_IDENTITY_BG[symbol] ?? 'bg-muted-foreground/30'
  const rsToneClass =
    rsIndexed == null
      ? 'text-muted-foreground'
      : rsIndexed > 100
        ? 'text-success-fg'
        : rsIndexed < 100
          ? 'text-danger-fg'
          : 'text-muted-foreground'
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={[
        'relative w-full text-left rounded-2xl bg-background shadow-inset-sm',
        'pl-3 pr-3 py-2.5 transition-all overflow-hidden',
        'hover:shadow-extruded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
        selected ? 'ring-2 ring-primary/40' : '',
      ].join(' ')}
    >
      <div
        aria-hidden
        className={`absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r ${barClass}`}
      />
      {/* Top row: rank · ticker+label · RS-indexed value + chevron */}
      <div className="flex items-center justify-between gap-2 pl-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-display font-bold text-sm tabular-nums text-foreground shrink-0 w-4 text-right">
            {rank ?? '—'}
          </span>
          <div className="min-w-0">
            <div className="font-mono font-semibold text-xs leading-tight">
              {symbol}
            </div>
            <div className="text-[10px] text-muted-foreground leading-tight truncate">
              {label}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span
            className={`font-mono text-xs tabular-nums ${rsToneClass}`}
          >
            {fmtRsIndexed(rsIndexed)}
          </span>
          <ChevronGlyph dir={momentum} />
        </div>
      </div>
      {/* Bottom row: z-score sparkline spanning full card width */}
      <div className="mt-1.5 pl-1.5">
        <Sparkline
          points={zScoreSeries}
          width={160}
          height={20}
          weekly={false}
          showPct={false}
        />
      </div>
    </button>
  )
}
