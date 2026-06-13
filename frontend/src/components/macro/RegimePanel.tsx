import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Sparkline } from '../charts/svg/Sparkline'
import { LineChart as RatioChart } from '../charts/plotly/LineChart'
import { useMacroRatio, useMacroSeries, useMacroSpread } from '../../hooks/use-api'
import {
  isRatioRow,
  isSeriesRow,
  isSpreadRow,
  rowSubtitle,
  type PanelIdentity,
  type RegimePanel as RegimePanelDef,
  type RegimeRow,
} from '../../lib/macro-views'

// Pre-computed Tailwind classes for the identity left-bar. Tailwind needs
// literal classnames at build time — can't interpolate `bg-identity-${x}`.
const IDENTITY_BAR_BG: Record<PanelIdentity, string> = {
  inflation: 'bg-identity-inflation',
  growth:    'bg-identity-growth',
  liquidity: 'bg-identity-liquidity',
  stress:    'bg-identity-stress',
  narrative: 'bg-identity-narrative',
  ambient:   'bg-identity-ambient',
}
import { ChevronDown, ChevronRight } from 'lucide-react'
import { InfoBubble } from '../common'

interface RegimePanelProps {
  panel: RegimePanelDef
  /** ISO date — when to start the chart. */
  since: string
}

// Hook router: a row is one of three shapes — ratio, series, or spread.
// Returns a uniform `points` array regardless of source.
function useRowData(row: RegimeRow, since: string, enabled = true) {
  const ratio = useMacroRatio({
    numerator: isRatioRow(row) ? row.numerator : '',
    denominator: isRatioRow(row) ? row.denominator : '',
    since,
    enabled: enabled && isRatioRow(row),
  })
  const series = useMacroSeries({
    symbol: isSeriesRow(row) ? row.symbol : '',
    since,
    enabled: enabled && isSeriesRow(row),
  })
  const spread = useMacroSpread({
    minuend: isSpreadRow(row) ? row.minuend : '',
    subtrahend: isSpreadRow(row) ? row.subtrahend : '',
    since,
    enabled: enabled && isSpreadRow(row),
  })
  if (isRatioRow(row)) {
    return {
      points: ratio.data?.points ?? [],
      isLoading: ratio.isLoading,
      isError: ratio.isError,
    }
  }
  if (isSpreadRow(row)) {
    return {
      points: spread.data?.points ?? [],
      isLoading: spread.isLoading,
      isError: spread.isError,
    }
  }
  return {
    points: series.data?.points ?? [],
    isLoading: series.isLoading,
    isError: series.isError,
  }
}

// Compact value formatter — keeps long FRED values (millions) readable.
function formatValue(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (abs >= 10_000) return `${(v / 1000).toFixed(1)}k`
  if (abs >= 100) return v.toFixed(1)
  if (abs >= 1) return v.toFixed(3)
  return v.toFixed(4)
}

function RegimeRowItem({ row, since }: { row: RegimeRow; since: string }) {
  const [expanded, setExpanded] = useState(false)
  const data = useRowData(row, since)
  const lastValue = data.points.length > 0 ? data.points[data.points.length - 1].value : null

  return (
    <div className="rounded-xl bg-background shadow-inset-sm">
      <div className="flex items-center justify-between gap-3 px-3 py-2 hover:bg-muted/30 transition-colors rounded-xl">
        {/* Toggle area — chevron + label/subtitle. Kept as a button for
            keyboard a11y. Info bubble lives OUTSIDE this button so its
            own button isn't nested (browsers reject that and swallow the
            inner button's hover events). */}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="flex items-center gap-2 min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-md"
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          )}
          <div className="min-w-0">
            <div className="text-sm font-medium leading-tight truncate">
              {row.label}
            </div>
            <div className="text-xs font-mono text-muted-foreground truncate">
              {rowSubtitle(row)}
            </div>
          </div>
        </button>
        {row.term && (
          <span className="shrink-0">
            <InfoBubble term={row.term} />
          </span>
        )}
        <div className="flex items-center gap-3 shrink-0">
          {lastValue != null && (
            <span className="text-xs font-mono tabular-nums text-foreground">
              {formatValue(lastValue)}
            </span>
          )}
          <Sparkline points={data.points} width={120} height={28} weekly />
        </div>
      </div>
      {expanded && (
        <div className="p-2 border-t border-muted-foreground/10">
          {data.isLoading ? (
            <div className="text-xs text-muted-foreground italic px-2 py-6 text-center">
              Loading…
            </div>
          ) : data.points.length === 0 ? (
            <div className="text-xs text-muted-foreground italic px-2 py-6 text-center">
              No cached data — try Refresh.
            </div>
          ) : (
            <RatioChart points={data.points} height={220} />
          )}
        </div>
      )}
    </div>
  )
}

export function RegimePanel({ panel, since }: RegimePanelProps) {
  // 4px identity left-bar — visual designer + UX strategist council
  // (2026-05-17). Pre-attentive regime classifier for the 6-panel grid.
  // Card stays clay; only the bar carries identity color.
  const barClass = IDENTITY_BAR_BG[panel.identity]
  return (
    <Card className="relative">
      <div
        aria-hidden
        className={`absolute left-0 top-0 bottom-0 w-1 rounded-l-3xl ${barClass}`}
      />
      <CardHeader className="pb-1 md:pb-1">
        {/* 2026-05-17 card-header consistency pass: Macro panel titles
            bumped to text-xl (20px) — operator audit picked Macro as the
            "good baseline, even bigger." Trailing gap dropped to pb-1
            (4px) — 67% reduction from the previous pb-3 (12px) — so the
            ratio rows start much closer to the regime label. */}
        <CardTitle className="text-xl flex items-center gap-1.5">
          {panel.title}
          {/* When the panel has a glossary term, the term's short/long copy
              covers what the blurb said — use the term. Otherwise fall
              back to inline blurb via the content prop. */}
          {panel.term
            ? <InfoBubble term={panel.term} />
            : <InfoBubble label={`${panel.title} — about`} content={panel.blurb} />}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {panel.rows.map((row) => (
          <RegimeRowItem key={row.id} row={row} since={since} />
        ))}
      </CardContent>
    </Card>
  )
}
