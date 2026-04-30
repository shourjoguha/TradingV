import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Sparkline } from './Sparkline'
import { RatioChart } from './RatioChart'
import { useMacroRatio, useMacroSeries } from '../../hooks/use-api'
import { sinceFromYears, type RegimePanel as RegimePanelDef, type RegimeRow } from '../../lib/macro-views'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface RegimePanelProps {
  panel: RegimePanelDef
  /** ISO date — when to start the chart. */
  since: string
  /** Years window for the focused chart's time-range chips. */
  focusedYears: number
}

// Hook router: a row is either a ratio (numerator/denominator) or a single
// series (symbol). Keeps the consumer simple.
function useRowData(row: RegimeRow, since: string, enabled = true) {
  const isRatio = 'numerator' in row
  const ratio = useMacroRatio({
    numerator: isRatio ? row.numerator : '',
    denominator: isRatio ? row.denominator : '',
    since,
    enabled: enabled && isRatio,
  })
  const series = useMacroSeries({
    symbol: !isRatio ? row.symbol : '',
    since,
    enabled: enabled && !isRatio,
  })
  return isRatio
    ? { points: ratio.data?.points ?? [], isLoading: ratio.isLoading, isError: ratio.isError }
    : { points: series.data?.points ?? [], isLoading: series.isLoading, isError: series.isError }
}

function rowSubtitle(row: RegimeRow): string {
  return 'numerator' in row ? `${row.numerator} ÷ ${row.denominator}` : row.symbol
}

function RegimeRowItem({ row, since }: { row: RegimeRow; since: string }) {
  const [expanded, setExpanded] = useState(false)
  const data = useRowData(row, since)
  const lastValue = data.points.length > 0 ? data.points[data.points.length - 1].value : null

  return (
    <div className="rounded-xl bg-background shadow-inset-sm">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left hover:bg-muted/30 transition-colors rounded-xl"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2 min-w-0">
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          )}
          <div className="min-w-0">
            <div className="text-sm font-medium leading-tight truncate">{row.label}</div>
            <div className="text-[10px] font-mono text-muted-foreground truncate">
              {rowSubtitle(row)}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {lastValue != null && (
            <span className="text-xs font-mono tabular-nums text-foreground">
              {formatValue(lastValue)}
            </span>
          )}
          <Sparkline points={data.points} width={120} height={28} weekly />
        </div>
      </button>
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

// Compact value formatter — keeps long FRED values (millions) readable.
function formatValue(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (abs >= 10_000) return `${(v / 1000).toFixed(1)}k`
  if (abs >= 100) return v.toFixed(1)
  if (abs >= 1) return v.toFixed(3)
  return v.toFixed(4)
}

export function RegimePanel({ panel, since }: RegimePanelProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{panel.title}</CardTitle>
        <CardDescription className="text-xs">{panel.blurb}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {panel.rows.map((row) => (
          <RegimeRowItem key={row.id} row={row} since={since} />
        ))}
      </CardContent>
    </Card>
  )
}
