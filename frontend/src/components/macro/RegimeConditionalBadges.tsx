/**
 * RegimeConditionalBadges — per-sector card showing how each sector reads
 * against the **current** cycle phase. Four states per sector:
 *
 *   ✓ Confirming           — favored phase = current AND leading SPY (RS > 100)
 *   ⚑ Out-of-phase leader  — favored phase ≠ current AND leading SPY (RS > 100)
 *   ✗ Failing canonical    — favored phase = current AND lagging SPY (RS < 100)
 *   · Quiet                — favored phase ≠ current AND lagging SPY (RS < 100)
 *
 * Operator scans for ⚑ (signal: regime in transition or sector-specific
 * catalyst) and ✗ (warning: canonical leaders not leading — breadth
 * divergence in the current phase).
 */
import { useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { InfoBubble } from '../common'
import { useMacroRatio, useMacroSeries } from '../../hooks/use-api'
import {
  SECTOR_ETFS,
  SECTOR_IDENTITY_BG,
} from '../../lib/macro-views'
import {
  detectCyclePhase,
  PHASES,
  SECTOR_PHASE,
} from '../../lib/sector-cycle'
import { rsIndexed } from '../../lib/sector-strength'
import type { MacroPoint } from '../../lib/types'

interface Props {
  since: string
}

type Verdict = 'confirming' | 'out-of-phase' | 'failing' | 'quiet'

const VERDICT_META: Record<
  Verdict,
  { label: string; glyph: string; tone: string; bg: string }
> = {
  confirming: {
    label: 'Confirming',
    glyph: '✓',
    tone: 'text-success-fg',
    bg: 'bg-success-bg/40',
  },
  'out-of-phase': {
    label: 'Out-of-phase leader',
    glyph: '⚑',
    tone: 'text-warning-fg',
    bg: 'bg-warning-bg/40',
  },
  failing: {
    label: 'Failing canonical',
    glyph: '✗',
    tone: 'text-danger-fg',
    bg: 'bg-danger-bg/40',
  },
  quiet: {
    label: 'Quiet',
    glyph: '·',
    tone: 'text-muted-foreground',
    bg: '',
  },
}

function verdictFor(
  favored: string,
  current: string,
  rs: number | null,
): Verdict {
  if (rs == null) return 'quiet'
  const leading = rs > 100
  const inPhase = favored === current
  if (inPhase && leading) return 'confirming'
  if (!inPhase && leading) return 'out-of-phase'
  if (inPhase && !leading) return 'failing'
  return 'quiet'
}

export function RegimeConditionalBadges({ since }: Props) {
  const xlk = useMacroRatio({ numerator: 'XLK', denominator: 'SPY', since })
  const xlf = useMacroRatio({ numerator: 'XLF', denominator: 'SPY', since })
  const xle = useMacroRatio({ numerator: 'XLE', denominator: 'SPY', since })
  const xlv = useMacroRatio({ numerator: 'XLV', denominator: 'SPY', since })
  const xli = useMacroRatio({ numerator: 'XLI', denominator: 'SPY', since })
  const xlp = useMacroRatio({ numerator: 'XLP', denominator: 'SPY', since })
  const xly = useMacroRatio({ numerator: 'XLY', denominator: 'SPY', since })
  const xlu = useMacroRatio({ numerator: 'XLU', denominator: 'SPY', since })
  const xlb = useMacroRatio({ numerator: 'XLB', denominator: 'SPY', since })
  const t10y2y = useMacroSeries({ symbol: 'T10Y2Y', since })

  const seriesBySymbol = useMemo<Record<string, MacroPoint[]>>(
    () => ({
      XLK: xlk.data?.points ?? [],
      XLF: xlf.data?.points ?? [],
      XLE: xle.data?.points ?? [],
      XLV: xlv.data?.points ?? [],
      XLI: xli.data?.points ?? [],
      XLP: xlp.data?.points ?? [],
      XLY: xly.data?.points ?? [],
      XLU: xlu.data?.points ?? [],
      XLB: xlb.data?.points ?? [],
    }),
    [
      xlk.data, xlf.data, xle.data, xlv.data, xli.data,
      xlp.data, xly.data, xlu.data, xlb.data,
    ],
  )

  const { phase: currentPhase } = useMemo(
    () => detectCyclePhase(t10y2y.data?.points ?? []),
    [t10y2y.data],
  )

  const rows = useMemo(() => {
    return SECTOR_ETFS.map(({ symbol, label }) => {
      const rs = rsIndexed(seriesBySymbol[symbol] ?? [])
      const favored = SECTOR_PHASE[symbol]
      const verdict = verdictFor(favored, currentPhase, rs)
      return { symbol, label, rs, favored, verdict }
    }).sort((a, b) => {
      // Priority order: out-of-phase > confirming > failing > quiet,
      // so the signal-rich rows surface first.
      const pri: Record<Verdict, number> = {
        'out-of-phase': 0,
        confirming: 1,
        failing: 2,
        quiet: 3,
      }
      if (pri[a.verdict] !== pri[b.verdict]) return pri[a.verdict] - pri[b.verdict]
      return (b.rs ?? -Infinity) - (a.rs ?? -Infinity)
    })
  }, [seriesBySymbol, currentPhase])

  return (
    <Card className="relative">
      <div
        aria-hidden
        className="absolute left-0 top-0 bottom-0 w-1 rounded-l-3xl bg-identity-narrative"
      />
      <CardHeader className="pb-1 md:pb-1">
        <CardTitle className="text-xl flex items-center gap-2">
          Phase confirmation
          <InfoBubble
            label="About Phase Confirmation"
            content={
              <>
                Each sector's current RS read against its canonical favored
                phase. ⚑ out-of-phase leader = signal worth investigating
                (regime transition or sector-specific catalyst). ✗ failing
                canonical = canonical leaders not leading = breadth
                divergence in current phase. Sorted by signal strength.
              </>
            }
          />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="text-xs text-muted-foreground">
          Current phase:{' '}
          <span className="font-semibold text-foreground">
            {PHASES[currentPhase].label}
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {rows.map((r) => {
            const meta = VERDICT_META[r.verdict]
            const barClass = SECTOR_IDENTITY_BG[r.symbol] ?? 'bg-muted-foreground/30'
            return (
              <div
                key={r.symbol}
                className={`relative rounded-2xl shadow-inset-sm bg-background ${meta.bg} pl-3 pr-3 py-2.5`}
                title={`${r.symbol} · favored: ${PHASES[r.favored].label} · current: ${PHASES[currentPhase].label}`}
              >
                <div
                  aria-hidden
                  className={`absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r ${barClass}`}
                />
                <div className="flex items-center justify-between gap-2 pl-1.5">
                  <div className="min-w-0">
                    <div className="font-mono font-semibold text-xs leading-tight flex items-center gap-1.5">
                      {r.symbol}
                      <span className={`text-xs ${meta.tone}`}>{meta.glyph}</span>
                    </div>
                    <div className="text-[10px] text-muted-foreground leading-tight truncate">
                      {meta.label} · favored {PHASES[r.favored].label}
                    </div>
                  </div>
                  <div
                    className={`font-mono text-xs tabular-nums shrink-0 ${
                      r.rs == null
                        ? 'text-muted-foreground'
                        : r.rs > 100
                          ? 'text-success-fg'
                          : 'text-danger-fg'
                    }`}
                  >
                    {r.rs == null
                      ? '—'
                      : `${r.rs > 100 ? '+' : ''}${(r.rs - 100).toFixed(1)}%`}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
