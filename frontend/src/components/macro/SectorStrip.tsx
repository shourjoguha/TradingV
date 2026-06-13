/**
 * SectorStrip — RS Leadership Ladder for the Macro › Sectors sub-tab.
 *
 * Replaces the prior bare 9-cell grid (2026-05-17 council pick — see
 * `~/.claude/plans/now-when-i-use-radiant-yao.md`). One vertical column of
 * cards, sorted by current relative-strength rank vs SPY. Each card shows
 * rank · ticker · z-scored RS sparkline · RS-indexed value · momentum
 * chevron. Click a card → expands the drill-in RatioChart + top holdings
 * (unchanged behaviour vs prior grid).
 *
 * Defensive-crowding cue: when 2+ of {XLP, XLU, XLV} crowd the top-3 RS
 * rank, the page surface receives a subtle stress-tinted wash — operator's
 * native "defensives rotating in" breadth-divergence signal.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMacroRatio, useQuotes } from '../../hooks/use-api'
import { LineChart as RatioChart } from '../charts/plotly/LineChart'
import { SectorLadderCard } from './SectorLadderCard'
import { SECTOR_ETFS } from '../../lib/macro-views'
import { SECTOR_HOLDINGS } from '../../lib/sector-holdings'
import type { MacroPoint } from '../../lib/types'
import {
  defensiveCrowding,
  latestValue,
  momentumDir,
  rsIndexed,
  rsMomentum,
  rsRankBySymbol,
  rsZScoreSeries,
} from '../../lib/sector-strength'
import { ExternalLink } from 'lucide-react'

// Open symbol on TradingView in a new tab. Holdings drill-out kept verbatim
// from the prior grid implementation — operator goes to TV/brokerage for
// richer per-ticker chart, no in-app duplicates.
function tradingViewHref(symbol: string): string {
  return `https://www.tradingview.com/symbols/${encodeURIComponent(symbol)}/`
}

function fmtClose(v: number | null | undefined): string {
  if (v == null) return '—'
  if (v >= 1000) return v.toFixed(0)
  return v.toFixed(2)
}

function fmtDeltaPct(v: number | null | undefined): string {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

interface SectorStripProps {
  since: string
}

export function SectorStrip({ since }: SectorStripProps) {
  // 9 stable-order hook calls — SECTOR_ETFS is module-const so hook order
  // never changes across renders. Each fetch is cached 5 min via
  // useMacroRatio; no extra backend cost vs prior grid (same 9 ratios).
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
      xlk.data,
      xlf.data,
      xle.data,
      xlv.data,
      xli.data,
      xlp.data,
      xly.data,
      xlu.data,
      xlb.data,
    ],
  )

  const ranks = useMemo(() => rsRankBySymbol(seriesBySymbol), [seriesBySymbol])
  const crowded = useMemo(() => defensiveCrowding(ranks), [ranks])

  // Per-sector derived cells. Pre-compute once per series change so the
  // sort below + the card props are stable identities (helps React keys
  // + downstream Sparkline memoization).
  type Cell = {
    symbol: string
    label: string
    rank: number | null
    indexed: number | null
    momentum: ReturnType<typeof momentumDir>
    zSeries: MacroPoint[]
    latest: number | null
  }
  const cells = useMemo<Cell[]>(() => {
    return SECTOR_ETFS.map(({ symbol, label }) => {
      const points = seriesBySymbol[symbol] ?? []
      return {
        symbol,
        label,
        rank: ranks[symbol] ?? null,
        indexed: rsIndexed(points),
        momentum: momentumDir(rsMomentum(points)),
        zSeries: rsZScoreSeries(points),
        latest: latestValue(points),
      }
    })
  }, [seriesBySymbol, ranks])

  // Sort: ranked sectors first (1 → 9), null-rank sectors at the bottom.
  const sortedCells = useMemo(() => {
    return [...cells].sort((a, b) => {
      if (a.rank == null && b.rank == null) return 0
      if (a.rank == null) return 1
      if (b.rank == null) return -1
      return a.rank - b.rank
    })
  }, [cells])

  // Always-on drill-in chart at the bottom — auto-selects the current
  // top-ranked sector on first render so the chart is never empty.
  // Clicking another sector swaps the active series.
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null)
  useEffect(() => {
    if (activeSymbol) return
    const topRanked = sortedCells.find((c) => c.rank != null)
    if (topRanked) setActiveSymbol(topRanked.symbol)
  }, [activeSymbol, sortedCells])
  const activeRatio = useMacroRatio({
    numerator: activeSymbol ?? '',
    denominator: 'SPY',
    since,
    enabled: !!activeSymbol,
  })

  const anyLoading =
    xlk.isLoading ||
    xlf.isLoading ||
    xle.isLoading ||
    xlv.isLoading ||
    xli.isLoading ||
    xlp.isLoading ||
    xly.isLoading ||
    xlu.isLoading ||
    xlb.isLoading

  return (
    <div
      className={[
        'space-y-4 rounded-3xl transition-colors duration-300',
        crowded ? 'bg-identity-stress/5 p-3' : '',
      ].join(' ')}
    >
      {crowded && (
        <div className="text-xs text-identity-stress font-medium px-1">
          Defensive crowding — 2+ of XLP/XLU/XLV in top-3 RS rank.
          Breadth-divergence signal active.
        </div>
      )}

      {anyLoading && cells.every((c) => c.latest == null) ? (
        <div className="text-xs text-muted-foreground italic p-4 text-center">
          Loading sector relative-strength…
        </div>
      ) : (
        // 3-col grid (mobile: 1 col, sm: 2 col, lg: 3 col) — compact card
        // pattern operator preferred; ladder math (rank · RS-indexed ·
        // chevron · sparkline) preserved inside each cell.
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {sortedCells.map((c) => (
            <SectorLadderCard
              key={c.symbol}
              symbol={c.symbol}
              label={c.label}
              rank={c.rank}
              zScoreSeries={c.zSeries}
              momentum={c.momentum}
              rsIndexed={c.indexed}
              selected={activeSymbol === c.symbol}
              onSelect={() => setActiveSymbol(c.symbol)}
            />
          ))}
        </div>
      )}

      {/* Always-on drill-in: chart for the currently-selected sector lives
          permanently at the bottom; auto-picks rank-1 on mount. Operator
          asked to keep this surface visible at all times. */}
      {activeSymbol && (
        <div className="rounded-2xl bg-background shadow-inset-sm p-3 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">
              {activeSymbol} / SPY{' '}
              <span className="text-muted-foreground font-mono text-xs">
                — relative-strength chart
              </span>
            </h3>
          </div>
          {activeRatio.isLoading ? (
            <div className="text-xs text-muted-foreground italic px-2 py-12 text-center">
              Loading…
            </div>
          ) : (activeRatio.data?.points.length ?? 0) === 0 ? (
            <div className="text-xs text-muted-foreground italic px-2 py-12 text-center">
              No cached data for this sector.
            </div>
          ) : (
            <RatioChart points={activeRatio.data!.points} height={260} />
          )}
          <SectorHoldings symbol={activeSymbol} />
        </div>
      )}
    </div>
  )
}

// Top-10 holdings + last close + 1w Δ% for the active sector. Verbatim
// from prior implementation — operator's drill-in expectation hasn't
// changed and the data path (`/v1/market_data/quotes`) is the same.
function SectorHoldings({ symbol }: { symbol: string }) {
  const holdings = SECTOR_HOLDINGS[symbol] ?? []
  const quotes = useQuotes(holdings)
  if (holdings.length === 0) return null

  const bySymbol = new Map(quotes.data?.items.map((q) => [q.symbol, q]) ?? [])

  return (
    <div className="space-y-2 pt-1">
      <h4 className="text-xs font-medium text-muted-foreground">
        Top holdings
      </h4>
      <div className="grid gap-1 grid-cols-1 sm:grid-cols-2">
        {holdings.map((sym) => {
          const q = bySymbol.get(sym)
          const pct = q?.pct_1w ?? null
          const pctClass =
            pct == null
              ? 'text-muted-foreground'
              : pct > 0
                ? 'text-success'
                : pct < 0
                  ? 'text-danger'
                  : 'text-muted-foreground'
          return (
            <a
              key={sym}
              href={tradingViewHref(sym)}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg bg-card hover:shadow-extruded-sm transition-shadow group"
              title={`Open ${sym} on TradingView`}
            >
              <span className="flex items-center gap-1.5 min-w-0">
                <span className="font-mono font-semibold text-xs">{sym}</span>
                <ExternalLink className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </span>
              <span className="flex items-center gap-3 shrink-0">
                <span className="text-xs font-mono tabular-nums text-foreground">
                  ${fmtClose(q?.last_close)}
                </span>
                <span
                  className={`text-xs font-mono tabular-nums w-16 text-right ${pctClass}`}
                >
                  {fmtDeltaPct(pct)}
                </span>
              </span>
            </a>
          )
        })}
      </div>
      <p className="text-xs text-muted-foreground italic">
        1-week Δ% from cached daily quote. Holdings list is hardcoded — see
        <span className="font-mono"> frontend/src/lib/sector-holdings.ts</span>.
      </p>
    </div>
  )
}
