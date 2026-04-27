import { useState } from 'react'
import { useOpportunities, useUpdateOpportunity, useCreateTrade } from '../hooks/use-api'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { Badge } from '../components/ui/badge'
import { Target, TrendingUp, TrendingDown, Receipt, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const TABS = [
  { id: 'open', label: 'Open' },
  { id: 'acted', label: 'Acted' },
  { id: 'dismissed', label: 'Dismissed' },
  { id: 'expired', label: 'Expired' },
] as const

function fmtPct(v: number, digits = 2) {
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

export function Opportunities() {
  const [tab, setTab] = useState<typeof TABS[number]['id']>('open')
  const opps = useOpportunities({ status: tab, limit: 200 })
  const update = useUpdateOpportunity()
  const createTrade = useCreateTrade()
  const navigate = useNavigate()
  const [dismissingId, setDismissingId] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  const handleAct = async (oppId: string, ticker: string, kind: 'buy' | 'sell') => {
    await update.mutateAsync({ id: oppId, status: 'acted' })
    // Optionally jump straight to log a trade prefilled.
    const goLog = window.confirm(`Log this ${kind.toUpperCase()} on ${ticker} as a trade?`)
    if (goLog) navigate(`/trades?from=${oppId}`)
  }

  const handleDismiss = (oppId: string) => {
    setDismissingId(oppId)
    setReason('')
  }

  const submitDismiss = async () => {
    if (!dismissingId) return
    await update.mutateAsync({ id: dismissingId, status: 'dismissed', reason })
    setDismissingId(null)
    setReason('')
  }

  const items = opps.data?.items ?? []

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-2xl font-bold tracking-tight">Opportunities</h2>
        <p className="text-sm text-muted-foreground">
          Signals from Kronos predictions that crossed a rule threshold AND have ≥60% historical hit-rate.
        </p>
      </div>

      <div className="inline-flex gap-1 p-1.5 rounded-2xl shadow-inset-sm bg-background">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium rounded-xl transition-all duration-200 ${
              tab === t.id ? 'bg-background shadow-extruded-sm text-violet' : 'text-muted-foreground hover:text-foreground'
            } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {opps.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : items.length === 0 ? (
        <div className="rounded-3xl shadow-inset-sm p-8 text-center text-muted-foreground bg-background">
          <Target className="h-8 w-8 mb-2 mx-auto text-muted-foreground/50" />
          <p className="text-sm">No {tab} opportunities.</p>
          {tab === 'open' && (
            <p className="text-xs mt-2">
              Generated automatically when predictions match an active rule.
              See <span className="font-mono">/v1/opportunities/generate</span> to trigger manually.
            </p>
          )}
        </div>
      ) : (
        <div className="rounded-2xl bg-background shadow-inset-sm p-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Ticker</th>
                <th className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Kind</th>
                <th className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Rule</th>
                <th className="text-right px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Move</th>
                <th className="text-right px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Conf</th>
                <th className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Generated</th>
                <th className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Expires</th>
                {tab === 'open' && <th className="text-right px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((o) => (
                <tr key={o.id} className="hover:bg-white/30">
                  <td className="px-3 py-2 font-mono">{o.ticker}</td>
                  <td className="px-3 py-2">
                    <Badge variant={o.kind === 'buy' ? 'success' : 'destructive'}>
                      {o.kind === 'buy' ? <TrendingUp className="h-3 w-3 mr-1" /> : <TrendingDown className="h-3 w-3 mr-1" />}
                      {o.kind.toUpperCase()}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{o.rule_label}</td>
                  <td className={`px-3 py-2 text-right font-mono ${o.predicted_move_pct > 0 ? 'text-success' : 'text-danger'}`}>
                    {fmtPct(o.predicted_move_pct)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{(o.confidence * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2 text-xs">{fmtDate(o.generated_at)}</td>
                  <td className="px-3 py-2 text-xs">{o.expires_at ? fmtDate(o.expires_at) : '—'}</td>
                  {tab === 'open' && (
                    <td className="px-3 py-2 text-right space-x-1">
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => handleAct(o.id, o.ticker, o.kind as 'buy' | 'sell')}
                        disabled={update.isPending}
                      >
                        <Receipt className="h-3 w-3 mr-1" /> Acted
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDismiss(o.id)}
                        disabled={update.isPending}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {dismissingId && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-6" onClick={() => setDismissingId(null)}>
          <div className="bg-background rounded-3xl shadow-extruded w-full max-w-md p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg">Dismiss opportunity</h3>
            <textarea
              autoFocus
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full bg-background rounded-2xl shadow-inset-sm p-3 text-sm h-24 placeholder:text-[#A0AEC0] focus:outline-none focus:shadow-inset focus:ring-2 focus:ring-violet"
              placeholder="Reason (optional)..."
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setDismissingId(null)}>Cancel</Button>
              <Button variant="primary" size="sm" onClick={submitDismiss} disabled={update.isPending}>Confirm dismiss</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
