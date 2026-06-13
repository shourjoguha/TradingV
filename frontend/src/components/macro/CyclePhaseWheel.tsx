/**
 * CyclePhaseWheel — 4-quadrant cycle wheel + sector dots. Tier-2 chart
 * (Plotly polar) since the Sectors viz is an expanded panel.
 *
 * Rewritten 2026-05-17 (Phase 5 of charts-plotly migration): domain wrapper
 * shapes `PolarQuadrant[]` + `PolarDot[]` and delegates rendering to
 * `<PolarRadial>` from the shared chart infra. Previously: pure inline SVG
 * w/ hand-rolled donut sector paths and polar→cartesian conversion (~150
 * LOC). Now: data prep only, native pan/hover/zoom from Plotly, ready for
 * future RRG-style continuous trails via the dots prop.
 *
 * Cycle semantics unchanged:
 *   1. *Where we are* — `detectCyclePhase(t10y2y)` infers current phase from
 *      the 10y-2y Treasury spread; active quadrant tints darker.
 *   2. *Where each sector belongs* — each of the 9 SPDR sectors is placed
 *      as a dot in its canonical-favored phase quadrant (Fidelity / SSGA
 *      taxonomy); dot size encodes current `rsIndexed` strength.
 */
import { useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { InfoBubble } from '../common'
import { useMacroSeries } from '../../hooks/use-api'
import {
  detectCyclePhase,
  PHASES,
  SECTOR_PHASE,
  type CyclePhase,
} from '../../lib/sector-cycle'
import { SECTOR_ETFS, SECTOR_IDENTITY_HEX } from '../../lib/macro-views'
import { rsIndexed } from '../../lib/sector-strength'
import { PolarRadial, type PolarDot, type PolarQuadrant } from '../charts/plotly/PolarRadial'
import { IDENTITY } from '../charts/theme/palette'
import type { MacroPoint } from '../../lib/types'

interface Props {
  since: string
}

/** Map RS-indexed (typically 80..120) → marker size in [6, 16] px. */
function dotRadius(rs: number | null, minR = 6, maxR = 16): number {
  if (rs == null) return minR
  const t = Math.max(0, Math.min(1, (rs - 80) / 40))
  return minR + t * (maxR - minR)
}

/** Place a sector dot deterministically inside its quadrant (sorted, inset). */
function dotsForPhase(
  phase: CyclePhase,
  sectorRs: Record<string, number | null>,
): Array<{ symbol: string; theta: number }> {
  const symbols = Object.entries(SECTOR_PHASE)
    .filter(([, p]) => p === phase)
    .map(([sym]) => sym)
    .sort()
  const { startAngle, endAngle } = PHASES[phase]
  const span = endAngle - startAngle
  const inset = span * 0.2
  const innerStart = startAngle + inset
  const innerEnd = endAngle - inset
  return symbols.map((symbol, i) => {
    const t = symbols.length === 1 ? 0.5 : i / (symbols.length - 1)
    const theta = innerStart + (innerEnd - innerStart) * t
    return { symbol, theta }
  })
  // (consumes sectorRs at the call site for sizing; signature kept narrow)
}

export function CyclePhaseWheel({ since }: Props) {
  const xlk = useMacroSeries({ symbol: 'XLK', since })
  const xlf = useMacroSeries({ symbol: 'XLF', since })
  const xle = useMacroSeries({ symbol: 'XLE', since })
  const xlv = useMacroSeries({ symbol: 'XLV', since })
  const xli = useMacroSeries({ symbol: 'XLI', since })
  const xlp = useMacroSeries({ symbol: 'XLP', since })
  const xly = useMacroSeries({ symbol: 'XLY', since })
  const xlu = useMacroSeries({ symbol: 'XLU', since })
  const xlb = useMacroSeries({ symbol: 'XLB', since })
  const spy = useMacroSeries({ symbol: 'SPY', since })
  const t10y2y = useMacroSeries({ symbol: 'T10Y2Y', since })

  const { phase, spread, trend } = useMemo(
    () => detectCyclePhase(t10y2y.data?.points ?? []),
    [t10y2y.data],
  )

  // Build per-sector RS-indexed values from raw closes vs SPY.
  const sectorRs = useMemo<Record<string, number | null>>(() => {
    const out: Record<string, number | null> = {}
    const sectorSeriesBySymbol: Record<string, MacroPoint[]> = {
      XLK: xlk.data?.points ?? [],
      XLF: xlf.data?.points ?? [],
      XLE: xle.data?.points ?? [],
      XLV: xlv.data?.points ?? [],
      XLI: xli.data?.points ?? [],
      XLP: xlp.data?.points ?? [],
      XLY: xly.data?.points ?? [],
      XLU: xlu.data?.points ?? [],
      XLB: xlb.data?.points ?? [],
    }
    const spyPoints = spy.data?.points ?? []
    if (spyPoints.length === 0) {
      for (const s of SECTOR_ETFS) out[s.symbol] = null
      return out
    }
    const spyByTs = new Map(spyPoints.map((p) => [p.ts, p.value]))
    for (const s of SECTOR_ETFS) {
      const series = sectorSeriesBySymbol[s.symbol]
      const ratioPoints: MacroPoint[] = []
      for (const p of series) {
        const spyVal = spyByTs.get(p.ts)
        if (spyVal != null && spyVal !== 0) {
          ratioPoints.push({ ts: p.ts, value: p.value / spyVal })
        }
      }
      out[s.symbol] = rsIndexed(ratioPoints)
    }
    return out
  }, [xlk.data, xlf.data, xle.data, xlv.data, xli.data, xlp.data, xly.data, xlu.data, xlb.data, spy.data])

  const activeMeta = PHASES[phase]

  // Shape quadrants for PolarRadial — active = narrative plum, inactive = grey.
  const quadrants = useMemo<PolarQuadrant[]>(
    () =>
      (Object.keys(PHASES) as CyclePhase[]).map((p) => {
        const meta = PHASES[p]
        const isActive = p === phase
        return {
          startDeg: meta.startAngle,
          endDeg: meta.endAngle,
          color: isActive ? IDENTITY.narrative : '#A0AEC0',
          label: meta.label,
          active: isActive,
        }
      }),
    [phase],
  )

  // Shape dots — each sector placed in its canonical-favored quadrant,
  // dot radius normalized to [0.55, 0.85] so they sit inside the donut band.
  const dots = useMemo<PolarDot[]>(() => {
    const out: PolarDot[] = []
    for (const ph of Object.keys(PHASES) as CyclePhase[]) {
      const placed = dotsForPhase(ph, sectorRs)
      for (const { symbol, theta } of placed) {
        const rs = sectorRs[symbol]
        out.push({
          theta,
          r: 0.7, // mid-band of the polar plot
          size: dotRadius(rs),
          color: SECTOR_IDENTITY_HEX[symbol] ?? '#A0AEC0',
          label: symbol,
          hover:
            rs != null
              ? `${symbol} — favored ${PHASES[ph].label}<br>RS ${(rs - 100).toFixed(1)}% vs SPY 1y`
              : `${symbol} — favored ${PHASES[ph].label}`,
        })
      }
    }
    return out
  }, [sectorRs])

  return (
    <Card className="relative">
      <div
        aria-hidden
        className="absolute left-0 top-0 bottom-0 w-1 rounded-l-3xl bg-identity-narrative"
      />
      <CardHeader className="pb-1 md:pb-1">
        <CardTitle className="text-xl flex items-center gap-2">
          Cycle phase
          <InfoBubble
            label="About the Cycle Phase Wheel"
            content={
              <>
                Current phase inferred from the 10y-2y Treasury spread.
                Each sector dot is placed in its canonical-favored phase
                (Fidelity / SSGA taxonomy); dot size scales with
                relative-strength vs SPY (1y indexed). Read: highlighted
                quadrant = where we are; dots in that quadrant = sectors
                whose thesis confirms; big dots outside = out-of-phase
                leadership (something to investigate).
              </>
            }
          />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col md:flex-row items-center md:items-start gap-4">
          {/* Plotly polar */}
          <div className="shrink-0 w-full md:w-[400px]">
            <PolarRadial
              quadrants={quadrants}
              dots={dots}
              centerText={{
                primary: activeMeta.label,
                secondary:
                  spread != null
                    ? `2s10s ${spread >= 0 ? '+' : ''}${spread.toFixed(2)} · ${trend ?? '—'}`
                    : undefined,
              }}
              height={400}
            />
          </div>

          {/* Sidekick: phase blurb + actionable read */}
          <div className="flex-1 min-w-0 space-y-3 text-sm">
            <div>
              <div className="text-xs font-mono text-muted-foreground">
                Current phase
              </div>
              <div className="text-lg font-semibold">{activeMeta.label}</div>
              <p className="text-xs text-muted-foreground leading-snug mt-1">
                {activeMeta.blurb}
              </p>
            </div>
            <div className="rounded-2xl bg-background shadow-inset-sm p-3 space-y-1.5">
              <div className="text-xs font-mono text-muted-foreground">
                How to read the wheel
              </div>
              <ul className="text-xs text-muted-foreground space-y-1 leading-snug">
                <li>
                  <span className="text-foreground font-medium">Big dots in highlighted quadrant</span> = sectors whose canonical phase matches the current cycle. Thesis-confirmed leadership.
                </li>
                <li>
                  <span className="text-foreground font-medium">Big dots outside</span> = out-of-phase leadership. Investigate: regime in transition, or a sector-specific catalyst overriding the cycle.
                </li>
                <li>
                  <span className="text-foreground font-medium">Small dots</span> in highlighted quadrant = canonical leaders failing to lead. Watch for breadth divergence.
                </li>
              </ul>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
