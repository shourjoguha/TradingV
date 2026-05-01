import { useState } from 'react'
import { useMacroRatio, useQuotes } from '../../hooks/use-api'
import { Sparkline } from './Sparkline'
import { RatioChart } from './RatioChart'
import { SECTOR_ETFS } from '../../lib/macro-views'
import { SECTOR_HOLDINGS } from '../../lib/sector-holdings'
import { ExternalLink } from 'lucide-react'

// Open symbol on TradingView in a new tab. No in-app charts for casual
// drill-in tickers — operator goes to their brokerage / TV for richer view.
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

interface SectorCellProps {
  symbol: string
  label: string
  since: string
  expanded: boolean
  onClick: () => void
}

function SectorCell({ symbol, label, since, expanded, onClick }: SectorCellProps) {
  const ratio = useMacroRatio({ numerator: symbol, denominator: 'SPY', since })
  const points = ratio.data?.points ?? []
  const first = points[0]?.value
  const last = points[points.length - 1]?.value
  const delta = first && last ? ((last - first) / first) * 100 : null

  // Neumorphic-friendly thresholds. Soft palette.
  let bgClass = 'bg-background shadow-inset-sm text-muted-foreground'
  if (delta != null) {
    if (delta > 1) bgClass = 'bg-success-bg text-success-fg shadow-extruded-sm'
    else if (delta < -1) bgClass = 'bg-danger-bg text-danger-fg shadow-extruded-sm'
    else bgClass = 'bg-warning-bg text-warning-fg shadow-extruded-sm'
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full px-3 py-3 rounded-2xl transition-transform hover:-translate-y-[1px] text-left overflow-hidden ${bgClass} ${
        expanded ? 'ring-2 ring-violet/40' : ''
      }`}
      aria-expanded={expanded}
    >
      <div className="flex items-center justify-between gap-2 mb-1 min-w-0">
        <span className="font-medium text-sm truncate">{label}</span>
        <span className="font-mono text-[10px] opacity-80 shrink-0">{symbol}</span>
      </div>
      <div className="flex items-center justify-between gap-2 overflow-hidden">
        <span className="font-mono text-xs tabular-nums">
          {delta == null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%`}
        </span>
        <Sparkline points={points} width={70} height={22} weekly showPct={false} />
      </div>
    </button>
  )
}

interface SectorStripProps {
  since: string
}

export function SectorStrip({ since }: SectorStripProps) {
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null)
  const activeRatio = useMacroRatio({
    numerator: activeSymbol ?? '',
    denominator: 'SPY',
    since,
    enabled: !!activeSymbol,
  })

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 sm:grid-cols-3 lg:grid-cols-9 gap-2">
        {SECTOR_ETFS.map(({ symbol, label }) => (
          <SectorCell
            key={symbol}
            symbol={symbol}
            label={label}
            since={since}
            expanded={activeSymbol === symbol}
            onClick={() => setActiveSymbol((s) => (s === symbol ? null : symbol))}
          />
        ))}
      </div>

      {activeSymbol && (
        <div className="rounded-2xl bg-background shadow-inset-sm p-3 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">
              {activeSymbol} / SPY <span className="text-muted-foreground font-mono text-xs">— relative-strength chart</span>
            </h3>
            <button
              type="button"
              onClick={() => setActiveSymbol(null)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Close
            </button>
          </div>
          {activeRatio.isLoading ? (
            <div className="text-xs text-muted-foreground italic px-2 py-12 text-center">Loading…</div>
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

// MW-3: top-10 holdings + last close + 1w Δ% for the active sector.
// Hardcoded holdings list (frontend/src/lib/sector-holdings.ts) avoids an
// ingestion pipeline; quote data comes from `ticker_market_data` via
// `/v1/market_data/quotes`. Click-out to TradingView for the chart.
function SectorHoldings({ symbol }: { symbol: string }) {
  const holdings = SECTOR_HOLDINGS[symbol] ?? []
  const quotes = useQuotes(holdings)
  if (holdings.length === 0) return null

  const bySymbol = new Map(quotes.data?.items.map((q) => [q.symbol, q]) ?? [])

  return (
    <div className="space-y-2 pt-1">
      <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
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
                <span className={`text-xs font-mono tabular-nums w-16 text-right ${pctClass}`}>
                  {fmtDeltaPct(pct)}
                </span>
              </span>
            </a>
          )
        })}
      </div>
      <p className="text-[10px] text-muted-foreground italic">
        1-week Δ% from cached daily quote. Holdings list is hardcoded — see
        <span className="font-mono"> frontend/src/lib/sector-holdings.ts</span>.
      </p>
    </div>
  )
}
