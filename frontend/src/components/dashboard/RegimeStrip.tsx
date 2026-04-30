import { Link } from 'react-router-dom'
import { useMacroRatio, useMacroSeries } from '../../hooks/use-api'
import { Sparkline } from '../macro/Sparkline'
import { REGIME_PANELS, sinceFromYears, type RegimeRow } from '../../lib/macro-views'
import { Card, CardContent } from '../ui/card'

// One inline tile per regime axis. Headline ratio for the axis = first row
// of each panel. Operator gets a 4-up regime glance without leaving Dashboard.
function HeadlineTile({ axis }: { axis: typeof REGIME_PANELS[number] }) {
  const headline = axis.rows[0] as RegimeRow
  const since = sinceFromYears(1) // 1y window — operator's "what changed lately"
  const isRatio = 'numerator' in headline
  const ratio = useMacroRatio({
    numerator: isRatio ? headline.numerator : '',
    denominator: isRatio ? headline.denominator : '',
    since,
    enabled: isRatio,
  })
  const series = useMacroSeries({
    symbol: !isRatio ? (headline as { symbol: string }).symbol : '',
    since,
    enabled: !isRatio,
  })
  const points = isRatio ? ratio.data?.points ?? [] : series.data?.points ?? []

  const first = points[0]?.value
  const last = points[points.length - 1]?.value
  const delta = first && last ? ((last - first) / first) * 100 : null
  const deltaColor =
    delta == null
      ? 'text-muted-foreground'
      : delta > 0
        ? 'text-success'
        : delta < 0
          ? 'text-danger'
          : 'text-muted-foreground'

  const subtitle = 'numerator' in headline
    ? `${headline.numerator} ÷ ${headline.denominator}`
    : (headline as { symbol: string }).symbol

  return (
    <Link
      to="/macro"
      className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet rounded-2xl"
    >
      <Card className="hover:-translate-y-[1px] transition-transform">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {axis.title}
            </span>
            <span className={`text-xs font-mono tabular-nums ${deltaColor}`}>
              {delta == null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%`}
            </span>
          </div>
          <div className="text-sm font-medium leading-tight truncate">{headline.label}</div>
          <div className="text-[10px] font-mono text-muted-foreground truncate mb-2">
            {subtitle} · 1y
          </div>
          <Sparkline points={points} width={180} height={28} weekly />
        </CardContent>
      </Card>
    </Link>
  )
}

export function RegimeStrip() {
  return (
    <div className="grid gap-3 grid-cols-2 lg:grid-cols-5">
      {REGIME_PANELS.map((axis) => (
        <HeadlineTile key={axis.title} axis={axis} />
      ))}
    </div>
  )
}
