import { useState } from 'react'
import {
  Copy,
  Check,
  Camera,
  Building2,
  Briefcase,
  Landmark,
  Activity,
  Info,
} from 'lucide-react'
import { useStreetDigest } from '../../hooks/use-api'
import { TickerLink } from '../common/TickerLink'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Skeleton } from '../ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import type {
  StreetDigestEntry,
  StreetDigestFundEntry,
  StreetDigestInsiderEntry,
  StreetDigestPoliticianEntry,
  StreetDigestOptionsEntry,
} from '../../lib/types'
import { toast } from 'sonner'

interface Props {
  symbol: string
  snapshotDate: string
  /** Skip the network round-trip until the parent expands. Defaults to true. */
  enabled?: boolean
}

/**
 * Pre-baked smart-money digest for one ticker × snapshot date.
 *
 * Data comes from `<vault>/The Street/data/<date>/digests.json` (built by
 * `tools/the_street/build_digests.py`) — no upstream API call. The digest
 * file is rebuilt automatically by the backend when stale.
 *
 * Each channel section renders structured rows; the copy button drops the
 * snapshot's pre-rendered Markdown into the clipboard for paste-into-vault.
 */
export function StreetDigestPanel({ symbol, snapshotDate, enabled = true }: Props) {
  const { data, isLoading } = useStreetDigest(snapshotDate, symbol, enabled)

  if (isLoading) {
    return <Skeleton className="h-32 w-full" />
  }
  if (!data || !data.found || !data.entry) {
    return (
      <div className="text-xs text-muted-foreground italic px-3 py-2">
        No raw breakdown available for {symbol} on {snapshotDate}.
      </div>
    )
  }
  return <DigestBody entry={data.entry} symbol={symbol} snapshotDate={snapshotDate} />
}

function DigestBody({
  entry,
  symbol,
  snapshotDate,
}: {
  entry: StreetDigestEntry
  symbol: string
  snapshotDate: string
}) {
  const [copied, setCopied] = useState(false)
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(entry.markdown)
      setCopied(true)
      toast.success(`${symbol} digest copied`)
      window.setTimeout(() => setCopied(false), 1500)
    } catch (err) {
      toast.error('Clipboard write failed')
    }
  }

  const ch = entry.channels
  const hasBil = (ch.billionaires?.length ?? 0) > 0
  const hasTb = (ch.trailblazers?.length ?? 0) > 0
  const hasIns = (ch.insiders?.length ?? 0) > 0
  const hasPol = (ch.politicians?.length ?? 0) > 0
  const hasOpt = (ch.options_bullish?.length ?? 0) > 0

  return (
    <div className="space-y-4 pb-2">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <TickerLink symbol={symbol} />
          {entry.company && entry.company.length > 1 && (
            <span className="text-xs text-muted-foreground">{entry.company}</span>
          )}
          <Badge variant="outline" className="text-xs">
            {entry.channel_count} channels
          </Badge>
          <Badge variant="outline" className="text-xs">
            {entry.total_signals} signals
          </Badge>
          <Badge variant="outline" className="text-xs">
            {snapshotDate}
          </Badge>
        </div>
        <Button size="sm" variant="ghost" onClick={onCopy} className="h-7">
          {copied ? (
            <Check className="h-3 w-3 mr-1 text-success" />
          ) : (
            <Copy className="h-3 w-3 mr-1" />
          )}
          {copied ? 'Copied' : 'Copy markdown'}
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {hasBil && (
          <Section
            label={`Billionaires (${ch.billionaires!.length})`}
            icon={<Briefcase className="h-3.5 w-3.5 text-primary" />}
            help="Named billionaires (Buffett, Tepper, Laffont, Sundheim, …) whose Q4 2025 13F filing showed an Added or New position. Quarterly cadence; ~45-day filing lag."
          >
            <FundList rows={ch.billionaires!} />
          </Section>
        )}
        {hasTb && (
          <Section
            label={`Trailblazers (${ch.trailblazers!.length})`}
            icon={<Building2 className="h-3.5 w-3.5 text-primary" />}
            help="High-performing fund managers tracked by the smart-money aggregator (51 funds). Same 13F cadence as Billionaires. Higher fund count = denser cross-fund crowding on this name."
          >
            <FundList rows={ch.trailblazers!} />
          </Section>
        )}
        {hasIns && (
          <Section
            label={`Insiders (${ch.insiders!.length})`}
            icon={<Camera className="h-3.5 w-3.5 text-primary" />}
            help="SEC Form-4 open-market buys by corporate officers and directors over the last ~60 days, ≥$100K. Treated as high-signal because insiders cannot legally trade on undisclosed material info."
          >
            <InsiderList rows={ch.insiders!} />
          </Section>
        )}
        {hasPol && (
          <Section
            label={`Politicians (${ch.politicians!.length})`}
            icon={<Landmark className="h-3.5 w-3.5 text-primary" />}
            help="STOCK Act disclosures by U.S. House/Senate members, ≥$100K, 90-day window. Buys only. Disclosure is a $-range, not a precise value. ~30-45 day lag from trade to disclosure."
          >
            <PoliticianList rows={ch.politicians!} />
          </Section>
        )}
        {hasOpt && (
          <Section
            label={`Options-Bullish (${ch.options_bullish!.length})`}
            icon={<Activity className="h-3.5 w-3.5 text-primary" />}
            help={OPTIONS_HELP}
          >
            <OptionsList rows={ch.options_bullish!} />
          </Section>
        )}
      </div>
    </div>
  )
}

const OPTIONS_HELP = (
  <>
    <p className="mb-2">
      Unusual call (or call-spread) flow flagged BULLISH by the smart-money
      aggregator, conviction ≥ 50, ~10-day rolling window. Bullish flow is
      positioning, not a literal share buy.
    </p>
    <ul className="space-y-1 list-disc pl-4">
      <li>
        <span className="font-mono">C$610.00 5/29</span> — Call, $610 strike,
        expires 2026-05-29. <span className="font-mono">P$…</span> would be a
        Put.
      </li>
      <li>
        <span className="font-medium">Premium</span> — total $ paid for the
        contract block. Bigger = larger account behind it.
      </li>
      <li>
        <span className="font-medium">Conviction</span> — the aggregator's blend
        of size, premium-vs-open-interest, and aggressor side. 50 = noisy, 70+ = strong.
      </li>
      <li>
        <span className="font-medium">vs OI</span> — sweep volume divided by
        existing open interest at that strike. {'>'}1× means more contracts
        traded than were already open — almost-by-definition new positioning.
      </li>
      <li>
        Near-term expiry (≤ 1 week) reads as a directional catalyst bet (often
        earnings); far-term expiry can be a hedge for an existing short.
      </li>
    </ul>
  </>
)

function Section({
  label,
  icon,
  children,
  help,
}: {
  label: string
  icon?: React.ReactNode
  children: React.ReactNode
  help?: React.ReactNode
}) {
  return (
    <div className="rounded-2xl shadow-inset-sm bg-background p-3 space-y-2">
      <div className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground">
        {icon}
        <span>{label}</span>
        {help && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label="Section help"
                className="ml-auto inline-flex items-center text-muted-foreground hover:text-primary"
                onClick={(e) => e.preventDefault()}
              >
                <Info className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" align="end" className="max-w-sm">
              <div className="text-xs">{help}</div>
            </TooltipContent>
          </Tooltip>
        )}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  )
}

function FundList({ rows }: { rows: StreetDigestFundEntry[] }) {
  return (
    <ul className="space-y-1 text-xs">
      {rows.map((r, i) => (
        <li key={`${r.fund}-${i}`} className="flex items-center justify-between gap-2">
          <span className="font-medium truncate">{r.fund}</span>
          <Badge variant="outline" className="text-xs shrink-0">
            {normaliseStatus(r.status)}
          </Badge>
        </li>
      ))}
    </ul>
  )
}

function InsiderList({ rows }: { rows: StreetDigestInsiderEntry[] }) {
  return (
    <ul className="space-y-2 text-xs">
      {rows.map((r, i) => (
        <li key={i} className="space-y-0.5">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium truncate">{r.person}</span>
            <span className="font-mono text-xs shrink-0">{r.value}</span>
          </div>
          <div className="text-xs text-muted-foreground">
            {r.title} · {r.shares} sh @ {r.price} · {r.date}
          </div>
        </li>
      ))}
    </ul>
  )
}

function PoliticianList({ rows }: { rows: StreetDigestPoliticianEntry[] }) {
  return (
    <ul className="space-y-2 text-xs">
      {rows.map((r, i) => {
        const partyDist = [r.party, r.district].filter(Boolean).join(' ')
        return (
          <li key={i} className="space-y-0.5">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium truncate">
                {r.member}
                {partyDist && (
                  <span className="text-muted-foreground"> ({partyDist})</span>
                )}
              </span>
              {r.fv && r.fv !== '—' && r.fv !== '-' && (
                <span
                  className={`font-mono text-xs shrink-0 ${
                    r.fv.startsWith('+') ? 'text-success' : 'text-danger'
                  }`}
                >
                  {r.fv}
                </span>
              )}
            </div>
            <div className="text-xs text-muted-foreground">
              {r.value_range} · traded {r.traded} · disclosed {r.disclosed}
              {r.committee ? ` · ${r.committee}` : ''}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function OptionsList({ rows }: { rows: StreetDigestOptionsEntry[] }) {
  return (
    <ul className="space-y-2 text-xs">
      {rows.map((r, i) => {
        const parsed = parseContract(r.contract)
        return (
          <li key={i} className="space-y-0.5">
            <div className="flex items-center justify-between gap-2">
              {parsed ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="cursor-help">
                      <span className="font-medium">
                        {parsed.kindLabel} ${parsed.strike}
                      </span>
                      <span className="text-muted-foreground">
                        {' '}→ {parsed.expiryLabel}
                      </span>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="max-w-xs">
                    <div className="text-xs space-y-1">
                      <div>
                        <span className="font-mono">{r.contract}</span>
                      </div>
                      <div>
                        <span className="font-medium">{parsed.kindLabel}</span>
                        : right to {parsed.kindAction} the underlying at{' '}
                        <span className="font-mono">${parsed.strike}</span> on
                        or before <span className="font-mono">{parsed.expiryLabel}</span>.
                      </div>
                      <div className="text-muted-foreground">
                        Bullish call sweeps signal directional positioning;
                        near-term expiry → catalyst bet, far-term → could be
                        a hedge.
                      </div>
                    </div>
                  </TooltipContent>
                </Tooltip>
              ) : (
                <span className="font-mono truncate">{r.contract}</span>
              )}
              <Badge variant="outline" className="text-xs shrink-0">
                conv {r.conviction}
              </Badge>
            </div>
            <div className="text-xs text-muted-foreground">
              {r.premium} premium · {r.ratio} vs OI · {r.date}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

interface ParsedContract {
  kind: 'C' | 'P'
  kindLabel: 'Call' | 'Put'
  kindAction: 'buy' | 'sell'
  strike: string // formatted
  expiryLabel: string // e.g. "May 29"
}

const MONTH_NAMES = [
  '',
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
]

/**
 * Parse the aggregator's compact contract code, e.g. `C$610.005/29` →
 * { kind:'C', strike:'610.00', expiryLabel:'May 29' }.
 *
 * Format observed: `[CP]$<strike-with-2-decimals><month>/<day>`. The
 * strike is glued to the month with no separator (e.g. `82.50` + `5/13`
 * renders as `82.505/13`), so the regex pins exactly two decimal digits
 * for the strike before the month.
 */
function parseContract(s: string | null | undefined): ParsedContract | null {
  if (!s) return null
  const m = /^([CP])\$(\d+\.\d{2})(\d{1,2})\/(\d{1,2})$/.exec(s.trim())
  if (!m) return null
  const [, kind, strike, mm, dd] = m
  const monthIdx = Math.max(1, Math.min(12, Number(mm)))
  return {
    kind: kind as 'C' | 'P',
    kindLabel: kind === 'C' ? 'Call' : 'Put',
    kindAction: kind === 'C' ? 'buy' : 'sell',
    strike,
    expiryLabel: `${MONTH_NAMES[monthIdx]} ${Number(dd)}`,
  }
}

function normaliseStatus(s: string): string {
  return s.replace(/[▲▼]/g, '').trim() || s
}
