/**
 * RotationFootprintStrip — sector-leadership-over-time bump chart.
 *
 * Rewritten 2026-05-18 (charts-enrichment): formerly a 12-column "top-3
 * sectors per week" identity-bar strip. Replaced w/ a smoothed bump chart
 * via the shared `<BumpChart>` Tier-2 primitive — each sector is a matte
 * identity-color line whose Y-position is its RS rank (1 = strongest) at
 * that week's close. Operator scans the lines: crossings = leadership
 * swaps, parallel lines = stable rank order, lines flat at the top =
 * persistent leadership.
 *
 * Y-axis carries sector symbols on BOTH sides (left = first-snapshot
 * landing, right = last-snapshot landing) per operator request — labels
 * are NOT repeated per bump, only at the start and end.
 *
 * Filename preserved (caller in `pages/Macro.tsx` Sectors dropdown still
 * imports `RotationFootprintStrip`); semantics changed.
 */
import { useMemo, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { InfoBubble } from '../common'
import { useMacroRatio } from '../../hooks/use-api'
import { SECTOR_ETFS } from '../../lib/macro-views'
import { weeklyRankMatrix } from '../../lib/sector-strength'
import { BumpChart, type BumpSeries } from '../charts/plotly/BumpChart'
import { SECTOR } from '../charts/theme/palette'
import { ChartTimeControl, type TimePreset } from '../charts/ChartTimeControl'
import type { MacroPoint } from '../../lib/types'

interface Props {
  since: string
}

/**
 * Bump-chart cadence + lookback presets. `daysPerPeriod` is the trading-day
 * stride between snapshots (5 = weekly, 21 = monthly, 63 = quarterly).
 * Operator picks the granularity that matches the rotation cadence they want
 * to study; longer lookbacks at coarser cadence show secular rotations
 * (e.g. 5y monthly = the cyclical rotation across one business cycle).
 *
 * Data ceiling is the page-level `since` chip — if you pick 5y here but the
 * page is set to 1Y, only 1Y of snapshots will render (graceful clamping in
 * `weeklyRankMatrix`).
 */
type CadenceId = '12w' | '26w' | '1y-m' | '3y-m' | '5y-m'
const CADENCE_PRESETS: Array<TimePreset<CadenceId> & { periods: number; daysPerPeriod: number }> = [
  { id: '12w',  label: '12w',     periods: 12, daysPerPeriod: 5 },
  { id: '26w',  label: '26w',     periods: 26, daysPerPeriod: 5 },
  { id: '1y-m', label: '1y · mo', periods: 12, daysPerPeriod: 21 },
  { id: '3y-m', label: '3y · mo', periods: 36, daysPerPeriod: 21 },
  { id: '5y-m', label: '5y · mo', periods: 60, daysPerPeriod: 21 },
]

export function RotationFootprintStrip({ since }: Props) {
  const [cadenceId, setCadenceId] = useState<CadenceId>('12w')
  const cadence = CADENCE_PRESETS.find((c) => c.id === cadenceId) ?? CADENCE_PRESETS[0]

  const xlk = useMacroRatio({ numerator: 'XLK', denominator: 'SPY', since })
  const xlf = useMacroRatio({ numerator: 'XLF', denominator: 'SPY', since })
  const xle = useMacroRatio({ numerator: 'XLE', denominator: 'SPY', since })
  const xlv = useMacroRatio({ numerator: 'XLV', denominator: 'SPY', since })
  const xli = useMacroRatio({ numerator: 'XLI', denominator: 'SPY', since })
  const xlp = useMacroRatio({ numerator: 'XLP', denominator: 'SPY', since })
  const xly = useMacroRatio({ numerator: 'XLY', denominator: 'SPY', since })
  const xlu = useMacroRatio({ numerator: 'XLU', denominator: 'SPY', since })
  const xlb = useMacroRatio({ numerator: 'XLB', denominator: 'SPY', since })

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

  const weeks = useMemo(
    () => weeklyRankMatrix(seriesBySymbol, cadence.periods, cadence.daysPerPeriod),
    [seriesBySymbol, cadence.periods, cadence.daysPerPeriod],
  )

  // Shape per-sector point arrays for the bump chart.
  const bumpSeries = useMemo<BumpSeries[]>(() => {
    return SECTOR_ETFS.map(({ symbol, label }) => ({
      id: symbol,
      label: `${symbol} · ${label}`,
      color: SECTOR[symbol] ?? '#A0AEC0',
      points: weeks.map((w) => ({ t: w.weekEnding, rank: w.ranks[symbol] ?? null })),
    }))
  }, [weeks])

  const empty = weeks.length === 0

  return (
    <Card className="relative">
      <div
        aria-hidden
        className="absolute left-0 top-0 bottom-0 w-1 rounded-l-3xl bg-identity-narrative"
      />
      <CardHeader className="pb-1 md:pb-1">
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <CardTitle className="text-xl flex items-center gap-2">
            Rotation footprint
            <InfoBubble
              label="About the Rotation Footprint"
              content={
                <>
                  Each line tracks one sector's relative-strength rank
                  over time (rank 1 = strongest vs SPY). Lines that cross
                  = leadership swaps; lines that stay parallel = stable
                  ordering. Sector labels on both sides of the Y-axis
                  show landing rank at start vs end of the window. Use
                  the cadence selector to flip between weekly (recent
                  rotation) and monthly (cyclical / regime rotation).
                  Data ceiling is the page-level time chip — pick 5y
                  there to unlock 5y monthly.
                </>
              }
            />
          </CardTitle>
          <ChartTimeControl
            value={cadenceId}
            onChange={setCadenceId}
            presets={CADENCE_PRESETS}
            ariaLabel="Rotation cadence and lookback"
          />
        </div>
      </CardHeader>
      <CardContent>
        {empty ? (
          <div className="text-xs text-muted-foreground italic p-4 text-center">
            Need 12 weeks of history + 1y lookback. Try a wider window.
          </div>
        ) : (
          <BumpChart series={bumpSeries} rankCount={SECTOR_ETFS.length} height={340} />
        )}
      </CardContent>
    </Card>
  )
}
