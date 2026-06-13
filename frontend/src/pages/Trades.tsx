import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTrades, useCreateTrade, useUpdateTrade, useOpportunities, useRxRecs } from '../hooks/use-api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Skeleton } from '../components/ui/skeleton'
import { Badge } from '../components/ui/badge'
import { Receipt, Plus, X } from 'lucide-react'
import { TickerLink } from '../components/common/TickerLink'
import { TradeCard } from '../components/trades/TradeCard'

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
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

export function Trades() {
  const [search, setSearch] = useSearchParams()
  const fromOpp = search.get('from')
  // rx v1.x.1-d: deep-link from rec detail. `?rec=<id>&ticker=<sym>`
  // opens the form prefilled, closing the prescription→action loop in
  // one click.
  const fromRecId = search.get('rec')
  const fromTicker = search.get('ticker')
  const trades = useTrades({ limit: 200 })
  const create = useCreateTrade()
  const update = useUpdateTrade()
  const opps = useOpportunities({ status: 'acted', limit: 200 })
  const [showForm, setShowForm] = useState(!!fromOpp || !!fromRecId)
  const [editingId, setEditingId] = useState<string | null>(null)

  const fromOppRow = useMemo(
    () => opps.data?.items.find((o) => o.id === fromOpp),
    [opps.data, fromOpp],
  )

  const closeForm = () => {
    setShowForm(false)
    if (fromRecId || fromTicker || fromOpp) {
      // Clear the deep-link query params so a re-open of /motion/trades
      // doesn't auto-pop the form again.
      const next = new URLSearchParams(search)
      next.delete('rec')
      next.delete('ticker')
      next.delete('from')
      setSearch(next, { replace: true })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold tracking-tight">Trades</h2>
          <p className="text-sm text-muted-foreground">
            Manual trade journal. Closed trades show realized P&L; open trades show entry only.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setShowForm(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Log trade
        </Button>
      </div>

      {trades.data?.pnl_summary && (
        <div className="grid grid-cols-3 gap-3">
          <SummaryCard label="Total P&L" value={fmtCur(trades.data.pnl_summary.total_realized_pnl)} accent />
          <SummaryCard label="Closed" value={String(trades.data.pnl_summary.closed_count)} />
          <SummaryCard label="Open" value={String(trades.data.pnl_summary.open_count)} />
        </div>
      )}

      {trades.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : (trades.data?.items.length ?? 0) === 0 ? (
        <div className="rounded-3xl shadow-inset-sm p-8 text-center text-muted-foreground bg-background">
          <Receipt className="h-8 w-8 mb-2 mx-auto text-muted-foreground/50" />
          <p className="text-sm">No trades logged yet.</p>
          <p className="text-xs mt-2">Log one from an Opportunity or via the "Log trade" button.</p>
        </div>
      ) : (
        <>
        {/* Mobile: stacked cards (table side-scrolls on phone, gap #5). */}
        <div className="md:hidden space-y-3">
          {trades.data!.items.map((t) => (
            <TradeCard key={t.id} trade={t} onClose={(id) => setEditingId(id)} />
          ))}
        </div>
        {/* Desktop: existing 9-column table. */}
        <div className="hidden md:block rounded-2xl bg-background shadow-inset-sm p-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Ticker</th>
                <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Side</th>
                <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Qty</th>
                <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Entry</th>
                <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Exit</th>
                <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">P&L</th>
                <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Rec</th>
                <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Entry at</th>
                <th className="text-right px-3 py-2 text-xs font-semibold text-muted-foreground">Action</th>
              </tr>
            </thead>
            <tbody>
              {trades.data!.items.map((t) => {
                // Win/loss identity bar — 3px left rail on closed rows.
                // growth=win (matches Macro/Growth identity hue, also
                // realized-positive) / stress=loss (matches invalidated
                // indicator). Open trades get no bar (undecided state).
                const pnl = t.realized_pnl ?? 0
                const barClass =
                  t.exit_price == null
                    ? null
                    : pnl > 0
                      ? 'bg-identity-growth'
                      : pnl < 0
                        ? 'bg-identity-stress'
                        : 'bg-muted-foreground/30'
                return (
                <tr key={t.id} className="hover:bg-white/30">
                  <td className="px-3 py-2 relative">
                    {barClass && (
                      <div
                        aria-hidden
                        className={`absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r ${barClass}`}
                      />
                    )}
                    <span className={barClass ? 'pl-1.5 inline-block' : ''}>
                      <TickerLink symbol={t.ticker} />
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant={t.side === 'buy' ? 'success' : 'destructive'}>{t.side.toUpperCase()}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{fmtNum(t.qty, 0)}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtNum(t.entry_price)}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtNum(t.exit_price)}</td>
                  <td className={`px-3 py-2 text-right font-mono ${
                    (t.realized_pnl ?? 0) > 0 ? 'text-success-fg font-semibold' : (t.realized_pnl ?? 0) < 0 ? 'text-danger-fg font-semibold' : ''
                  }`}>
                    {fmtCur(t.realized_pnl)}
                  </td>
                  <td className="px-3 py-2">
                    {t.related_rec_id ? (
                      <Link
                        to={`/motion/recs/${t.related_rec_id}`}
                        className="font-mono text-[11px] text-primary hover:underline"
                      >
                        {t.related_rec_id.slice(0, 8)}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs">{fmtDate(t.entry_at)}</td>
                  <td className="px-3 py-2 text-right">
                    {t.exit_price == null ? (
                      <Button size="sm" variant="outline" onClick={() => setEditingId(t.id)}>Close</Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">closed</span>
                    )}
                  </td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        </>
      )}

      {showForm && (
        <TradeForm
          oppContext={fromOppRow}
          prefillTicker={fromTicker ?? undefined}
          prefillRecId={fromRecId ?? undefined}
          onClose={closeForm}
          onSubmit={async (data) => {
            await create.mutateAsync(data)
            closeForm()
          }}
        />
      )}

      {editingId && (
        <ExitForm
          tradeId={editingId}
          onClose={() => setEditingId(null)}
          onSubmit={async (data) => {
            await update.mutateAsync({ id: editingId, ...data })
            setEditingId(null)
          }}
        />
      )}
    </div>
  )
}

function SummaryCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`rounded-3xl shadow-extruded-sm p-4 bg-background ${accent ? 'text-primary' : ''}`}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-display font-extrabold tabular-nums mt-1">{value}</div>
    </div>
  )
}

function TradeForm({ oppContext, prefillTicker, prefillRecId, onClose, onSubmit }: {
  oppContext?: any
  prefillTicker?: string
  prefillRecId?: string
  onClose: () => void
  onSubmit: (data: any) => Promise<void>
}) {
  // Default entry_at to today (operator-local). Stored as YYYY-MM-DD; on
  // submit we attach midday UTC so timezone rounding never shifts the date
  // ahead/back. The backend's `entry_at` field is optional and defaults to
  // NOW() — passing an explicit ISO ts gives the operator backdating power.
  const todayIso = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({
    ticker: (oppContext?.ticker ?? prefillTicker ?? '').toUpperCase(),
    side: oppContext?.kind ?? 'buy',
    qty: '',
    entry_price: '',
    fees: '',
    notes_md: oppContext ? `From opportunity ${oppContext.rule_label}` : (prefillRecId ? `From recommendation ${prefillRecId.slice(0, 8)}` : ''),
    opportunity_id: oppContext?.id ?? '',
    related_rec_id: prefillRecId ?? '',
    entry_date: todayIso,
  })
  const set = (k: string, v: any) => setForm({ ...form, [k]: v })
  // rx v1.x.1-b: pull recent finance recs for the autocomplete dropdown.
  // window=30d matches the brief's "recommendations WHERE created_at > NOW - INTERVAL '30 days'".
  const recRecs = useRxRecs({ window_days: 30, limit: 100 })
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-6" onClick={onClose}>
      <div className="bg-background rounded-3xl shadow-extruded w-full max-w-md p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Log trade</h3>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Ticker</Label>
            <Input value={form.ticker} onChange={(e) => set('ticker', e.target.value.toUpperCase())} />
          </div>
          <div>
            <Label>Side</Label>
            <select value={form.side} onChange={(e) => set('side', e.target.value)} className="w-full bg-background rounded-2xl shadow-inset-sm px-3 py-2 text-sm focus:outline-none focus:shadow-inset focus:ring-2 focus:ring-primary">
              <option value="buy">BUY</option>
              <option value="sell">SELL</option>
            </select>
          </div>
          <div>
            <Label>Qty</Label>
            <Input type="number" value={form.qty} onChange={(e) => set('qty', e.target.value)} />
          </div>
          <div>
            <Label>Entry price</Label>
            <Input type="number" step="0.01" value={form.entry_price} onChange={(e) => set('entry_price', e.target.value)} />
          </div>
          <div>
            <Label>Fees</Label>
            <Input type="number" step="0.01" value={form.fees} onChange={(e) => set('fees', e.target.value)} />
          </div>
          <div>
            <Label>Entry date</Label>
            <Input
              type="date"
              value={form.entry_date}
              max={todayIso}
              onChange={(e) => set('entry_date', e.target.value)}
            />
          </div>
        </div>
        <div>
          <Label>Notes</Label>
          <textarea
            value={form.notes_md}
            onChange={(e) => set('notes_md', e.target.value)}
            className="w-full bg-background rounded-2xl shadow-inset-sm p-3 text-sm h-20 placeholder:text-[#A0AEC0] focus:outline-none focus:shadow-inset focus:ring-2 focus:ring-primary"
          />
        </div>
        {/* rx v1.x.1-b: link to the rec that prompted this trade. */}
        {(recRecs.data?.items.length ?? 0) > 0 && (
          <div>
            <Label>Related rec (optional)</Label>
            <select
              value={form.related_rec_id}
              onChange={(e) => set('related_rec_id', e.target.value)}
              className="w-full bg-background rounded-2xl shadow-inset-sm px-3 py-2 text-sm focus:outline-none focus:shadow-inset focus:ring-2 focus:ring-primary"
            >
              <option value="">(none)</option>
              {recRecs.data!.items.map((r) => {
                const drift = r.drift_score != null ? r.drift_score.toFixed(2) : '—'
                const status = r.forced_decision ? `⚠ ${r.status}` : r.status
                const tldr = r.tldr_short ?? '(no tldr)'
                return (
                  <option key={r.id} value={r.id}>
                    {r.short_id} · drift {drift} · {status} · {tldr}
                  </option>
                )
              })}
            </select>
            <p className="text-xs text-muted-foreground mt-1">
              Powers the position_thesis_match signal in /rx-finance.
            </p>
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="sm" onClick={() => {
            // Attach midday UTC to the date — keeps the local-day intent stable
            // across DST shifts and TZ rounding on display. When the operator
            // logs trades same-day (the common case) this is indistinguishable
            // from NOW(); when backdating, it pins the date the operator chose.
            const entryAt = form.entry_date
              ? new Date(`${form.entry_date}T12:00:00Z`).toISOString()
              : undefined
            onSubmit({
              ticker: form.ticker,
              side: form.side,
              qty: parseFloat(form.qty),
              entry_price: parseFloat(form.entry_price),
              fees: form.fees ? parseFloat(form.fees) : 0,
              notes_md: form.notes_md || undefined,
              opportunity_id: form.opportunity_id || undefined,
              related_rec_id: form.related_rec_id || undefined,
              entry_at: entryAt,
            })
          }}>Save</Button>
        </div>
      </div>
    </div>
  )
}

function ExitForm({ tradeId: _id, onClose, onSubmit }: { tradeId: string; onClose: () => void; onSubmit: (data: any) => Promise<void> }) {
  const [exitPrice, setExitPrice] = useState('')
  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-6" onClick={onClose}>
      <div className="bg-background rounded-3xl shadow-extruded w-full max-w-sm p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-display font-bold text-lg">Close trade</h3>
        <div>
          <Label>Exit price</Label>
          <Input autoFocus type="number" step="0.01" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="sm" onClick={() => onSubmit({ exit_price: parseFloat(exitPrice), exit_at: new Date().toISOString() })}>Close trade</Button>
        </div>
      </div>
    </div>
  )
}
