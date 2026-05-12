import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useStreetTier } from '../../hooks/use-api'
import { TickerLink } from '../common/TickerLink'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { Skeleton } from '../ui/skeleton'
import { StreetDigestPanel } from './StreetDigestPanel'
import type { StreetTierRow } from '../../lib/types'

interface Props {
  tier: 1 | 2 | 3
  date?: string
  includeEtfs?: boolean
}

const TIER_LABELS: Record<1 | 2 | 3, string> = {
  1: 'Tier 1 — 4+ channel cross-conviction',
  2: 'Tier 2 — 3-channel conviction',
  3: 'Tier 3 — 2-channel + ≥5 Trailblazers cluster',
}

/**
 * Tier table — one row per ticker. Click a row to expand a structured
 * smart-money digest (per-channel breakdown + copy-to-markdown button)
 * sourced from the pre-baked snapshot digests.json. Notable column is
 * truncated; full detail lives in the expanded panel.
 */
export function TierTable({ tier, date, includeEtfs }: Props) {
  const { data, isLoading } = useStreetTier(tier, { date, includeEtfs })
  const [openTicker, setOpenTicker] = useState<string | null>(null)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{TIER_LABELS[tier]}</CardTitle>
        {data?.snapshot_date && (
          <Badge variant="outline" className="w-fit text-[10px]">
            Snapshot {data.snapshot_date}
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : !data || data.items.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No Tier {tier} rows in this snapshot.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                <tr className="border-b border-foreground/10">
                  <th className="w-6 py-2"></th>
                  <th className="text-left px-2 py-2">Ticker</th>
                  <th className="text-right px-2 py-2">Bil</th>
                  <th className="text-right px-2 py-2">TB</th>
                  <th className="text-right px-2 py-2">Ins</th>
                  <th className="text-right px-2 py-2">Pol</th>
                  <th className="text-right px-2 py-2">Opt</th>
                  <th className="text-right px-2 py-2">Sig</th>
                  <th className="text-left px-2 py-2">Notable</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <TierRow
                    key={r.ticker}
                    row={r}
                    snapshotDate={data.snapshot_date ?? ''}
                    isOpen={openTicker === r.ticker}
                    onToggle={() =>
                      setOpenTicker((cur) => (cur === r.ticker ? null : r.ticker))
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function TierRow({
  row,
  snapshotDate,
  isOpen,
  onToggle,
}: {
  row: StreetTierRow
  snapshotDate: string
  isOpen: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer border-b border-foreground/5 hover:bg-foreground/5 transition-colors"
      >
        <td className="py-2 pl-2 text-muted-foreground">
          {isOpen ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </td>
        <td className="px-2 py-2 font-mono">
          <TickerLink symbol={row.ticker} />
        </td>
        <td className="px-2 py-2 text-right font-mono text-xs">
          {row.billionaires || ''}
        </td>
        <td className="px-2 py-2 text-right font-mono text-xs">
          {row.trailblazers || ''}
        </td>
        <td className="px-2 py-2 text-right font-mono text-xs">
          {row.insiders || ''}
        </td>
        <td className="px-2 py-2 text-right font-mono text-xs">
          {row.politicians || ''}
        </td>
        <td className="px-2 py-2 text-right font-mono text-xs">
          {row.options_bullish || ''}
        </td>
        <td className="px-2 py-2 text-right font-mono text-xs font-semibold">
          {row.total_signals}
        </td>
        <td
          className={`px-2 py-2 text-xs text-muted-foreground min-w-0 ${
            isOpen
              ? 'whitespace-normal break-words'
              : 'truncate max-w-[16rem] xl:max-w-[24rem]'
          }`}
        >
          {row.notable}
        </td>
      </tr>
      {isOpen && (
        <tr className="bg-foreground/5">
          <td colSpan={9} className="px-4 py-3">
            <StreetDigestPanel
              symbol={row.ticker}
              snapshotDate={snapshotDate}
              enabled={isOpen}
            />
          </td>
        </tr>
      )}
    </>
  )
}
