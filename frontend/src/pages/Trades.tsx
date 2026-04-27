import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTrades, useCreateTrade, useUpdateTrade, useOpportunities } from '../hooks/use-api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Skeleton } from '../components/ui/skeleton'
import { Badge } from '../components/ui/badge'
import { Receipt, Plus, X } from 'lucide-react'

function fmtCur(v: number | null | undefined, digits = 2) {
  if (v == null || !isFinite(v)) return '—'
  return v.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: digits, maximumFractionDigits: digits })
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
  const [search] = useSearchParams()
  const fromOpp = search.get('from')
  const trades = useTrades({ limit: 200 })
  const create = useCreateTrade()
  const update = useUpdateTrade()
  const opps = useOpportunities({ status: 'acted', limit: 200 })
  const [showForm, setShowForm] = useState(!!fromOpp)
  const [editingId, setEditingId] = useState<string | null>(null)

  const fromOppRow = useMemo(
    () => opps.data?.items.find((o) => o.id === fromOpp),
    [opps.data, fromOpp],
  )

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Trades</h2>
          <p className="text-sm text-muted-foreground">
            Manual trade journal. Closed trades show realized P&L; open trades show entry only.
          </p>
        </div>
        <Button size="sm" onClick={() => setShowForm(true)}>
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
        <div className="border rounded p-8 text-center text-muted-foreground border-dashed">
          <Receipt className="h-8 w-8 mb-2 mx-auto text-muted-foreground/50" />
          <p className="text-sm">No trades logged yet.</p>
          <p className="text-xs mt-2">Log one from an Opportunity or via the "Log trade" button.</p>
        </div>
      ) : (
        <div className="border rounded overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr>
                <th className="text-left px-3 py-2">Ticker</th>
                <th className="text-left px-3 py-2">Side</th>
                <th className="text-right px-3 py-2">Qty</th>
                <th className="text-right px-3 py-2">Entry</th>
                <th className="text-right px-3 py-2">Exit</th>
                <th className="text-right px-3 py-2">P&L</th>
                <th className="text-left px-3 py-2">Entry at</th>
                <th className="text-right px-3 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {trades.data!.items.map((t) => (
                <tr key={t.id} className="border-t">
                  <td className="px-3 py-2 font-mono">{t.ticker}</td>
                  <td className="px-3 py-2">
                    <Badge variant={t.side === 'buy' ? 'default' : 'destructive'}>{t.side.toUpperCase()}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{fmtNum(t.qty, 0)}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtNum(t.entry_price)}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtNum(t.exit_price)}</td>
                  <td className={`px-3 py-2 text-right font-mono ${
                    (t.realized_pnl ?? 0) > 0 ? 'text-green-400' : (t.realized_pnl ?? 0) < 0 ? 'text-red-400' : ''
                  }`}>
                    {fmtCur(t.realized_pnl)}
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
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <TradeForm
          oppContext={fromOppRow}
          onClose={() => setShowForm(false)}
          onSubmit={async (data) => {
            await create.mutateAsync(data)
            setShowForm(false)
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
    <div className={`border rounded p-4 ${accent ? 'border-primary/40 bg-primary/5' : ''}`}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold font-mono mt-1">{value}</div>
    </div>
  )
}

function TradeForm({ oppContext, onClose, onSubmit }: {
  oppContext?: any
  onClose: () => void
  onSubmit: (data: any) => Promise<void>
}) {
  const [form, setForm] = useState({
    ticker: oppContext?.ticker ?? '',
    side: oppContext?.kind ?? 'buy',
    qty: '',
    entry_price: '',
    fees: '',
    notes_md: oppContext ? `From opportunity ${oppContext.rule_label}` : '',
    opportunity_id: oppContext?.id ?? '',
  })
  const set = (k: string, v: any) => setForm({ ...form, [k]: v })
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-6" onClick={onClose}>
      <div className="bg-card border rounded-lg w-full max-w-md p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
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
            <select value={form.side} onChange={(e) => set('side', e.target.value)} className="w-full bg-background border rounded px-2 py-2 text-sm">
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
        </div>
        <div>
          <Label>Notes</Label>
          <textarea
            value={form.notes_md}
            onChange={(e) => set('notes_md', e.target.value)}
            className="w-full bg-background border rounded p-2 text-sm h-20"
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => onSubmit({
            ticker: form.ticker,
            side: form.side,
            qty: parseFloat(form.qty),
            entry_price: parseFloat(form.entry_price),
            fees: form.fees ? parseFloat(form.fees) : 0,
            notes_md: form.notes_md || undefined,
            opportunity_id: form.opportunity_id || undefined,
          })}>Save</Button>
        </div>
      </div>
    </div>
  )
}

function ExitForm({ tradeId: _id, onClose, onSubmit }: { tradeId: string; onClose: () => void; onSubmit: (data: any) => Promise<void> }) {
  const [exitPrice, setExitPrice] = useState('')
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-6" onClick={onClose}>
      <div className="bg-card border rounded-lg w-full max-w-sm p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-semibold">Close trade</h3>
        <div>
          <Label>Exit price</Label>
          <Input autoFocus type="number" step="0.01" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => onSubmit({ exit_price: parseFloat(exitPrice), exit_at: new Date().toISOString() })}>Close trade</Button>
        </div>
      </div>
    </div>
  )
}
