import { useTradePositions, type PositionItem } from '../hooks/use-api'
import { Skeleton } from '../components/ui/skeleton'
import { Badge } from '../components/ui/badge'
import { AlertTriangle, BarChart3, Link2 } from 'lucide-react'
import { PageHeader } from '../components/common/PageHeader'
import { PageWithSidecar } from '../components/common/DetailSidecar'
import { PositionsSidecar } from '../components/rx/PositionsSidecar'

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

function fmtSignedCur(v: number) {
  const sign = v >= 0 ? '+' : ''
  return `${sign}${fmtCur(v)}`
}

function pnlColor(v: number | null | undefined): string {
  if (v == null || v === 0) return 'text-muted-foreground'
  return v > 0 ? 'text-success-fg' : 'text-danger-fg'
}

export function RxFinancePositions() {
  const q = useTradePositions({ limit: 200 })

  const main = (
    <div className="space-y-4">
      <PageHeader
        icon={BarChart3}
        title="Open positions"
        description="Aggregated from open trades. Current price = latest daily OHLCV close; falls back to avg entry when no quote cached."
      />

      {q.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : (q.data?.items.length ?? 0) === 0 ? (
        <div className="rounded-3xl shadow-inset-sm p-8 text-center text-muted-foreground bg-background">
          <BarChart3 className="h-8 w-8 mb-2 mx-auto text-muted-foreground/50" />
          <p className="text-sm">No open positions.</p>
          <p className="text-xs mt-2">Log a trade from <code>/motion/trades</code>; positions aggregate from open trades automatically.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Card label="Portfolio value">{fmtCur(q.data!.portfolio_total_value, { compact: true })}</Card>
            <Card label="Unrealized P&L">
              <span className={pnlColor(q.data!.portfolio_unrealized_pnl)}>
                {fmtSignedCur(q.data!.portfolio_unrealized_pnl)}
              </span>
            </Card>
            <Card label="Open positions">{q.data!.count}</Card>
          </div>

          <div className="rounded-2xl bg-background shadow-inset-sm p-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Ticker</th>
                  <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Qty</th>
                  <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Avg entry</th>
                  <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Current</th>
                  <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Value</th>
                  <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">P&L</th>
                  <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">% book</th>
                  <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Flags</th>
                </tr>
              </thead>
              <tbody>
                {q.data!.items.map((p: PositionItem) => (
                  <tr key={p.ticker} className="border-t border-border/40">
                    <td className="px-3 py-2 font-mono font-semibold">{p.ticker}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{p.qty.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtCur(p.avg_price)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {p.current_price != null
                        ? fmtCur(p.current_price)
                        : <span className="text-muted-foreground text-xs">stale</span>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtCur(p.current_value, { compact: true })}</td>
                    <td className={`px-3 py-2 text-right tabular-nums ${pnlColor(p.unrealized_pnl)}`}>
                      <div>{fmtSignedCur(p.unrealized_pnl)}</div>
                      {p.unrealized_pnl_pct != null && (
                        <div className="text-xs opacity-70">{fmtPct(p.unrealized_pnl_pct)}</div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtPct(p.pct_portfolio)}</td>
                    <td className="px-3 py-2 space-x-2">
                      {p.risk_flag_single && (
                        <Badge variant="outline" className="text-red-700 border-red-600 bg-red-500/10 text-xs">
                          <AlertTriangle className="h-3 w-3 mr-1" /> &gt;5%
                        </Badge>
                      )}
                      {p.has_rec_link && (
                        <Badge variant="outline" className="text-blue-700 border-blue-500/40 text-xs">
                          <Link2 className="h-3 w-3 mr-1" /> rec
                        </Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">
            Sector concentration flag not computed (no sector data in TradingV). Single-position flag suppressed when portfolio is small or count of positions is low — see service.RISK_FLAG_MIN_* constants.
          </p>
        </>
      )}
    </div>
  )

  return <PageWithSidecar main={main} sidecar={<PositionsSidecar />} />
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-3xl bg-background shadow-extruded-sm p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-display font-extrabold tabular-nums mt-1">{children}</div>
    </div>
  )
}
