import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  useRxRec,
  useDispositionRec,
  useSnoozeRec,
  useRxLinks,
  type RxDispositionAction,
} from '../hooks/use-api'
import { Button } from '../components/ui/button'
import { Label } from '../components/ui/label'
import { Skeleton } from '../components/ui/skeleton'
import { Badge } from '../components/ui/badge'
import { StatusBadge } from '../components/common/StatusBadge'
import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Clock,
  Eye,
  FlaskConical,
  Receipt,
} from 'lucide-react'

// Pull a likely ticker from the rec text for the "Log trade from this rec"
// prefill. Mirrors the server's denylist in app/rx/service.py so the UI
// doesn't suggest "BUY" or "USA" as tickers.
const TICKER_NOISE_DENYLIST = new Set([
  'AI', 'API', 'BUY', 'CEO', 'CFO', 'CPI', 'CPU', 'DCF', 'EBIT', 'EBITDA',
  'EOD', 'ETF', 'FAQ', 'FED', 'FOMC', 'GDP', 'GPU', 'HOLD', 'IPO', 'IRR',
  'LBO', 'MA', 'OPEN', 'OTC', 'PE', 'PMI', 'ROI', 'RSI', 'SELL', 'SP',
  'SPX', 'SP500', 'SPY', 'TBD', 'TLDR', 'UK', 'US', 'USA', 'VIX', 'WSJ',
  'YOY', 'YTD',
])

function guessTicker(tldr: string | null | undefined, body: string | null | undefined): string | null {
  const haystack = `${tldr ?? ''} ${body ?? ''}`
  const matches = haystack.match(/\b[A-Z]{2,5}\b/g) ?? []
  for (const m of matches) {
    if (!TICKER_NOISE_DENYLIST.has(m)) return m
  }
  return null
}

export function RxFinanceDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const rec = useRxRec(id)
  const links = useRxLinks(id)
  const disp = useDispositionRec()
  const snz = useSnoozeRec()
  const [fit, setFit] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [snoozeDays, setSnoozeDays] = useState(1)
  const [showJson, setShowJson] = useState(false)
  const [pendingAction, setPendingAction] = useState<RxDispositionAction | null>(null)
  // Disposition wash (Phase 5 color taxonomy) — one-shot 320ms ease-out
  // card-bg lerp on success, then settle. Receipt for the operator that
  // the verb landed in the ledger. Three variants: success/snooze/dismiss.
  const [washClass, setWashClass] = useState<string | null>(null)

  function fireWash(kind: 'success' | 'snooze' | 'dismiss') {
    const cls =
      kind === 'success' ? 'animate-disposition-wash-success'
      : kind === 'snooze' ? 'animate-disposition-wash-snooze'
      : 'animate-disposition-wash-dismiss'
    setWashClass(cls)
    window.setTimeout(() => setWashClass(null), 350)
  }

  if (rec.isLoading) return <Skeleton className="h-60 w-full" />
  if (rec.error || !rec.data) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/motion/recs')}>
          <ArrowLeft className="h-4 w-4 mr-2" /> Back
        </Button>
        <p className="text-sm text-muted-foreground">Rec not found.</p>
      </div>
    )
  }

  const r = rec.data
  const forcedDecision = r.forced_decision
  const guessedTicker = guessTicker(r.tldr, r.body_md)
  // Build the "Log trade" deep-link with ticker prefill + rec linkage.
  const tradeHref = `/motion/trades?rec=${r.id}${guessedTicker ? `&ticker=${guessedTicker}` : ''}`

  const submit = (action: RxDispositionAction) => {
    if ((action === 'acted_as_prescribed' || action === 'acted_modified') && fit == null) {
      setPendingAction(action)
      return
    }
    const washKind: 'success' | 'dismiss' =
      action.startsWith('acted') ? 'success' : 'dismiss'
    disp.mutate(
      {
        id: r.id,
        body: {
          disposition: action,
          subjective_fit_1_5: fit ?? undefined,
          outcome_note: note || undefined,
        },
      },
      { onSuccess: () => fireWash(washKind) },
    )
    setPendingAction(null)
  }

  const statusValue =
    r.status === 'snoozed' && r.snoozed_until && new Date(r.snoozed_until) < new Date()
      ? 'auto_revived'
      : r.status
  const statusBadge = <StatusBadge kind="rec" value={statusValue} />

  return (
    <div className="relative space-y-6">
      {/* Disposition wash overlay — one-shot 320ms ease-out. Sits behind
          content (pointer-events none) so the operator's click flow is
          uninterrupted; gives a body-receipt the verb committed. */}
      {washClass && (
        <div
          aria-hidden
          className={`pointer-events-none fixed inset-0 z-0 rounded-3xl ${washClass}`}
        />
      )}
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => navigate('/motion/recs')}>
          <ArrowLeft className="h-4 w-4 mr-2" /> Back to recommendations
        </Button>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="font-mono text-xs">{r.id.slice(0, 8)}</Badge>
          {statusBadge}
        </div>
      </div>

      {forcedDecision && (
        <div className="rounded-xl border border-danger/50 bg-danger/10 px-3 py-2 text-xs text-danger-fg flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="font-medium">Forced decision</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">
            snoozed {r.snooze_count}× — pick a disposition, don't snooze again
          </span>
        </div>
      )}

      {/* Inline meta strip (2026-05-17 density audit): replaced a 3-stat
          card-of-cards grid that ate ~100px of vertical space for 3
          numbers. Same data, one line, reads as a contextual footer. */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground tabular-nums font-mono">
        <span>
          drift{' '}
          <span className="text-foreground font-semibold">
            {r.drift_score != null ? r.drift_score.toFixed(2) : '—'}
          </span>
        </span>
        <span className="text-muted-foreground/40">·</span>
        <span>
          conf <span className="text-foreground font-semibold">{r.confidence ?? '—'}</span>
        </span>
        <span className="text-muted-foreground/40">·</span>
        <span title={new Date(r.created_at).toLocaleString()}>
          {new Date(r.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })}
        </span>
      </div>

      {/* Phase 2: Operator-attention axis. Shows when TV-context items (note/
          idea/screenshot/event/webhook) in the last 14d mention any ticker
          this rec discusses. Closes the feedback loop: operator sees WHY
          this rec ranked higher than another. */}
      {r.attention_score != null && r.attention_score > 0 && r.attention_breakdown && (
        <div className="rounded-2xl border border-primary/30 bg-primary/5 p-4 flex items-start gap-3">
          <Eye className="h-5 w-5 mt-0.5 shrink-0 text-primary" />
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline justify-between gap-2">
              <strong className="text-sm text-foreground">Operator attention</strong>
              <span className="text-xs text-muted-foreground font-mono">
                score {r.attention_score.toFixed(2)} · last 14d
              </span>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {Object.entries(r.attention_breakdown).map(([ticker, b], i, arr) => {
                const parts: string[] = []
                const s = (b.screenshot ?? 0); if (s) parts.push(`${s} screenshot${s > 1 ? 's' : ''}`)
                const n = (b.note ?? 0); if (n) parts.push(`${n} note${n > 1 ? 's' : ''}`)
                const idea = (b.idea ?? 0); if (idea) parts.push(`${idea} idea${idea > 1 ? 's' : ''}`)
                const ev = (b.event ?? 0); if (ev) parts.push(`${ev} event${ev > 1 ? 's' : ''}`)
                const wh = (b.webhook ?? 0); if (wh) parts.push(`${wh} alert${wh > 1 ? 's' : ''}`)
                if (parts.length === 0) return null
                return (
                  <span key={ticker}>
                    <span className="font-mono text-foreground">{ticker}</span>:{' '}
                    {parts.join(' + ')}
                    {i < arr.length - 1 ? ' · ' : ''}
                  </span>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Combined TLDR + body card — operator reads them as one thought */}
      {(r.tldr || r.body_md) && (
        <article className="rounded-2xl bg-background shadow-inset-sm p-6 docs-article max-w-none space-y-4">
          {r.tldr && (
            <p className="text-base font-medium text-foreground border-l-4 border-primary pl-4 m-0">
              {r.tldr}
            </p>
          )}
          {r.body_md && <ReactMarkdown remarkPlugins={[remarkGfm]}>{r.body_md}</ReactMarkdown>}
        </article>
      )}

      {/* Action CTAs: trade + promote-to-thesis. Both prefill via URL.
          2026-05-17 density audit: collapsed from twin framed cards (each
          w/ subtitle copy explaining the verb) to a flat button row;
          hover tooltips carry the prefill explanation. */}
      {(r.status === 'open' || r.status === 'snoozed') && (
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={tradeHref}
            title={guessedTicker
              ? `Pre-fills ${guessedTicker} + this rec into the trade form`
              : 'Opens trade form linked to this rec'}
          >
            <Button size="sm" variant="primary">
              <Receipt className="h-4 w-4 mr-2" />
              Log trade
            </Button>
          </Link>
          <Link
            to={`/theses?from_rec=${r.id}${guessedTicker ? `&ticker=${guessedTicker}` : ''}`}
            title="Crystallise this rec into a hypothesis on /theses"
          >
            <Button size="sm" variant="outline">
              <FlaskConical className="h-4 w-4 mr-2" />
              Promote to thesis
            </Button>
          </Link>
        </div>
      )}

      {/* Snooze history — only visible when this rec has been snoozed at least once */}
      {r.snooze_count > 0 && (
        <div className="rounded-2xl bg-background shadow-inset-sm p-4 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              Snooze history
            </h3>
            <span className="text-xs text-muted-foreground tabular-nums">
              {r.snooze_count} snooze{r.snooze_count === 1 ? '' : 's'}
            </span>
          </div>
          {r.snoozed_until && (
            <p className="text-xs text-muted-foreground">
              {new Date(r.snoozed_until) < new Date()
                ? <>Last snooze window expired {new Date(r.snoozed_until).toLocaleString()} — rec is auto-revived.</>
                : <>Currently snoozed until {new Date(r.snoozed_until).toLocaleString()}.</>}
            </p>
          )}
          {r.snooze_count >= 2 && (
            <p className="text-xs text-red-700">
              Forced-decision threshold reached. Snoozing again does not extend the rec's useful window.
            </p>
          )}
        </div>
      )}

      {r.rx_md_path && (
        <p className="text-xs text-muted-foreground">
          Source: <code>{r.rx_md_path}</code> (laptop filesystem)
        </p>
      )}

      <div className="rounded-2xl bg-background shadow-inset-sm p-3">
        <button
          className="flex items-center gap-2 text-sm font-semibold w-full text-left"
          onClick={() => setShowJson((v) => !v)}
        >
          {showJson ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Breakdowns + signals
        </button>
        {showJson && (
          <pre className="mt-3 text-[11px] bg-muted/30 rounded-lg p-3 overflow-x-auto">
{JSON.stringify(
  {
    signals_fired: r.signals_fired,
    drift_breakdown: r.drift_breakdown,
    confidence_breakdown: r.confidence_breakdown,
    facts_json: r.facts_json,
    source_refs: r.source_refs,
  },
  null,
  2,
)}
          </pre>
        )}
      </div>

      {/* Hypothesis + trade cross-references (v1.x.1-b) */}
      {(links.data?.hypotheses.length || links.data?.trades.length) ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {links.data!.hypotheses.length > 0 && (
            <div className="rounded-2xl bg-background shadow-inset-sm p-4">
              <h3 className="text-sm font-semibold mb-2">Related hypotheses</h3>
              <ul className="space-y-1 text-sm">
                {links.data!.hypotheses.map((h) => (
                  <li key={h.id} className="flex items-center justify-between">
                    <span>{h.title}</span>
                    <StatusBadge kind="hypothesis" value={h.status} size="xs" />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {links.data!.trades.length > 0 && (
            <div className="rounded-2xl bg-background shadow-inset-sm p-4">
              <h3 className="text-sm font-semibold mb-2">Related trades</h3>
              <ul className="space-y-1 text-sm">
                {links.data!.trades.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-3">
                    <span className="font-mono">{t.ticker} · {t.side} {t.qty} @ {t.entry_price}</span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(t.entry_at).toLocaleDateString()}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : null}

      {/* Disposition panel — hide once rec is terminal. Reordered (P2-L):
          buttons first (decide), then fit (rate), then note (annotate),
          then snooze (defer) as a clearly separated row. */}
      {(r.status === 'open' || r.status === 'snoozed') && (
        <div className="rounded-2xl bg-background shadow-inset-sm p-4 space-y-4">
          <h3 className="text-sm font-semibold">Disposition</h3>

          <div className="flex flex-wrap gap-2">
            <Button
              variant="default"
              className="bg-success hover:bg-success-fg text-white"
              disabled={disp.isPending}
              onClick={() => submit('acted_as_prescribed')}
            >
              Acted as prescribed
            </Button>
            <Button
              variant="default"
              className="bg-success/70 hover:bg-success text-white"
              disabled={disp.isPending}
              onClick={() => submit('acted_modified')}
            >
              Acted modified
            </Button>
            <Button variant="secondary" disabled={disp.isPending} onClick={() => submit('skipped')}>
              Skipped
            </Button>
            <Button variant="ghost" disabled={disp.isPending} onClick={() => submit('dismissed')}>
              Dismiss
            </Button>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Subjective fit (1-5) — required when marking as acted</Label>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  className={`h-8 w-8 rounded-md text-sm font-mono border ${
                    fit === n
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'border-border hover:bg-muted'
                  }`}
                  onClick={() => setFit(n)}
                >
                  {n}
                </button>
              ))}
              {fit != null && (
                <Button variant="ghost" size="sm" onClick={() => setFit(null)}>
                  clear
                </Button>
              )}
            </div>
            {pendingAction && fit == null && (
              <p className="text-xs text-red-600">Fit 1-5 required for acted_* dispositions.</p>
            )}
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Outcome note (optional, ≤280 chars)</Label>
            <textarea
              maxLength={280}
              className="w-full text-sm rounded-md border border-border bg-background p-2 min-h-[60px]"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>

          <div className="border-t pt-4 flex items-end gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Snooze for N days (1-7)</Label>
              <select
                className="h-9 rounded-md border border-border bg-background px-2 text-sm"
                value={snoozeDays}
                onChange={(e) => setSnoozeDays(Number(e.target.value))}
              >
                {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                  <option key={d} value={d}>{d}d</option>
                ))}
              </select>
            </div>
            <Button
              variant="outline"
              className="text-blue-700 border-blue-500/40"
              disabled={snz.isPending}
              onClick={() =>
                snz.mutate(
                  { id: r.id, days: snoozeDays },
                  { onSuccess: () => fireWash('snooze') },
                )
              }
            >
              <Clock className="h-4 w-4 mr-2" />
              Snooze
            </Button>
            {r.snooze_count > 0 && (
              <span className="text-xs text-muted-foreground">snoozed {r.snooze_count}× already</span>
            )}
          </div>
        </div>
      )}

      {/* Terminal state read-only summary */}
      {(r.status === 'acted' || r.status === 'dismissed') && (
        <div className="rounded-2xl bg-background shadow-inset-sm p-4 text-sm text-muted-foreground">
          {r.acted_at && (
            <p>
              <strong>{r.acted_disposition}</strong> at {new Date(r.acted_at).toLocaleString()}
              {r.subjective_fit_1_5 != null && <> · fit {r.subjective_fit_1_5}/5</>}
            </p>
          )}
          {r.outcome_note && <p className="mt-2 italic">"{r.outcome_note}"</p>}
        </div>
      )}
    </div>
  )
}

// Local <Card label> stat helper retired 2026-05-17 — drift/conf/created
// fields now render as a single inline meta strip near the title (density
// audit). If a future stat needs a framed badge, use the shadcn <Card>
// primitive directly with custom padding/typography.
