/**
 * TradeCard — mobile-stacked trade card.
 *
 * Mirror of RecCard for the Trades table. The 9-column table
 * (`Trades.tsx`) side-scrolls on <md viewports; this card renders the
 * same signal vertically so flags + P&L are visible on phone.
 *
 * Gap #5 from session audit (2026-05-17). Used in Trades.tsx with the
 * `md:hidden` / `hidden md:block` responsive pattern matching RxFinance.
 */
import { Link } from 'react-router-dom'
import type { Trade } from '../../lib/types'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { TickerLink } from '../common/TickerLink'

function fmtCur(v: number | null | undefined, digits = 2) {
  if (v == null || !isFinite(v)) return '—'
  return v.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

function fmtNum(v: number | null | undefined, digits = 2) {
  if (v == null || !isFinite(v)) return '—'
  return v.toFixed(digits)
}

function fmtDate(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: '2-digit',
  })
}

export function TradeCard({
  trade,
  onClose,
}: {
  trade: Trade
  onClose?: (id: string) => void
}) {
  const pnl = trade.realized_pnl
  const pnlColor = pnl == null ? 'text-muted-foreground' : pnl > 0 ? 'text-success-fg' : pnl < 0 ? 'text-danger-fg' : 'text-muted-foreground'
  const closed = trade.exit_price != null
  // Win/loss identity bar — matches desktop table (Phase 4c color taxonomy).
  const barClass = !closed
    ? null
    : (pnl ?? 0) > 0
      ? 'bg-identity-growth'
      : (pnl ?? 0) < 0
        ? 'bg-identity-stress'
        : 'bg-muted-foreground/30'
  return (
    <div className="relative rounded-2xl bg-background shadow-inset-sm p-4 pl-5 space-y-2">
      {barClass && (
        <div
          aria-hidden
          className={`absolute left-0 top-2 bottom-2 w-[3px] rounded-r ${barClass}`}
        />
      )}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <TickerLink symbol={trade.ticker} />
          <Badge variant={trade.side === 'buy' ? 'success' : 'destructive'}>
            {trade.side.toUpperCase()}
          </Badge>
        </div>
        <span className="text-xs text-muted-foreground tabular-nums">
          {fmtDate(trade.entry_at)}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-x-3 gap-y-1.5 text-xs">
        <div>
          <div className="text-xs text-muted-foreground">Qty</div>
          <div className="tabular-nums">{fmtNum(trade.qty, 0)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Entry</div>
          <div className="tabular-nums">{fmtCur(trade.entry_price)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">
            {closed ? 'Exit' : 'Status'}
          </div>
          <div className="tabular-nums">
            {closed ? fmtCur(trade.exit_price) : <span className="text-muted-foreground">open</span>}
          </div>
        </div>
      </div>

      {pnl != null && (
        <div className={`text-sm font-semibold tabular-nums ${pnlColor}`}>
          {pnl > 0 ? '+' : ''}{fmtCur(pnl)} <span className="text-xs opacity-70 font-normal">P&amp;L</span>
        </div>
      )}

      <div className="flex items-center justify-between gap-2 pt-1">
        {trade.related_rec_id ? (
          <Link
            to={`/motion/recs/${trade.related_rec_id}`}
            className="font-mono text-[11px] text-primary hover:underline"
          >
            rec {trade.related_rec_id.slice(0, 8)}
          </Link>
        ) : (
          <span className="text-xs text-muted-foreground">no rec link</span>
        )}
        {!closed && onClose && (
          <Button size="sm" variant="outline" onClick={() => onClose(trade.id)}>
            Close
          </Button>
        )}
      </div>
    </div>
  )
}
