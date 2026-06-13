/**
 * PositionsSidecar — right-rail context for /motion/positions.
 *
 * Tiles:
 *   - Concentration distribution — bar per ticker showing %book
 *   - Total cost vs total value — quick ROI snapshot
 *   - Risk thresholds reference
 */
import { useTradePositions, type PositionItem } from '../../hooks/use-api'
import { SidecarTile } from '../common/DetailSidecar'

function fmtCur(v: number | null | undefined, opts: { compact?: boolean } = {}) {
  if (v == null || !isFinite(v)) return '—'
  return v.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: opts.compact ? 0 : 2,
    maximumFractionDigits: 2,
  })
}

function fmtPct(v: number | null | undefined, digits = 1) {
  if (v == null || !isFinite(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

export function PositionsSidecar() {
  const { data } = useTradePositions({ limit: 200 })
  const items = data?.items ?? []
  const sortedByPct = [...items].sort((a, b) => b.pct_portfolio - a.pct_portfolio)
  const topThree = sortedByPct.slice(0, 5)
  const totalCost = items.reduce((s, p) => s + Math.abs(p.cost_basis), 0)
  const totalValue = data?.portfolio_total_value ?? 0
  const totalPnl = data?.portfolio_unrealized_pnl ?? 0
  const totalPnlPct = totalCost > 0 ? totalPnl / totalCost : null

  return (
    <>
      <SidecarTile label="Concentration">
        {items.length === 0 ? (
          <p className="text-xs text-muted-foreground">No open positions.</p>
        ) : (
          <div className="space-y-2">
            {topThree.map((p: PositionItem) => (
              <ConcRow key={p.ticker} ticker={p.ticker} pct={p.pct_portfolio} />
            ))}
            {items.length > 5 && (
              <p className="text-xs text-muted-foreground pt-1">
                + {items.length - 5} more position{items.length - 5 === 1 ? '' : 's'}
              </p>
            )}
          </div>
        )}
      </SidecarTile>

      <SidecarTile label="Cost basis vs value">
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-muted-foreground">Total cost</span>
            <span className="text-sm tabular-nums">{fmtCur(totalCost, { compact: true })}</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-muted-foreground">Current value</span>
            <span className="text-sm tabular-nums">{fmtCur(totalValue, { compact: true })}</span>
          </div>
          <div className="flex items-baseline justify-between pt-1 border-t border-border/30">
            <span className="text-xs text-muted-foreground">Unrealized</span>
            <span
              className={`text-base font-display font-bold tabular-nums ${
                totalPnl > 0 ? 'text-success-fg' : totalPnl < 0 ? 'text-danger-fg' : ''
              }`}
            >
              {totalPnl >= 0 ? '+' : ''}{fmtCur(totalPnl, { compact: true })}
              {totalPnlPct != null && (
                <span className="text-xs ml-1 opacity-70">({fmtPct(totalPnlPct)})</span>
              )}
            </span>
          </div>
        </div>
      </SidecarTile>

      <SidecarTile label="Risk thresholds">
        <ul className="text-xs text-muted-foreground space-y-2">
          <li>
            <span className="text-foreground">&gt;5%</span> single-position flag fires only when
            portfolio ≥ $5k AND ≥4 positions.
          </li>
          <li>
            <span className="text-foreground">Sector concentration</span> not computed — no sector
            lookup table in TradingV (v1.x.1-c gap).
          </li>
          <li>
            Source-of-truth: <code className="text-xs">Lakshmi/01_rules/risk_rules.md</code>
          </li>
        </ul>
      </SidecarTile>
    </>
  )
}

function ConcRow({ ticker, pct }: { ticker: string; pct: number }) {
  const w = Math.max(0, Math.min(1, pct)) * 100
  const tone = pct > 0.05 ? 'bg-amber-500/60' : 'bg-muted-foreground/40'
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs mb-0.5">
        <span className="font-mono">{ticker}</span>
        <span className="tabular-nums">{fmtPct(pct)}</span>
      </div>
      <div className="h-1 rounded-full bg-muted overflow-hidden">
        <div className={`h-full ${tone}`} style={{ width: `${w}%` }} />
      </div>
    </div>
  )
}
