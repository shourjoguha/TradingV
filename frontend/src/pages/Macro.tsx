import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '../components/ui/toggle-group'
import { useMacroRatio, useMacroRefresh, useMacroSeries } from '../hooks/use-api'
import { RegimePanel } from '../components/macro/RegimePanel'
import { SectorStrip } from '../components/macro/SectorStrip'
import { RatioChart } from '../components/macro/RatioChart'
import {
  REGIME_PANELS,
  TIME_RANGE_OPTIONS,
  sinceFromYears,
  type RegimeRow,
} from '../lib/macro-views'
import { RefreshCw, LineChart as LineChartIcon } from 'lucide-react'
import { InfoBubble } from '../components/common'

type Tab = 'overview' | 'ratios' | 'sectors'
const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'ratios',   label: 'Ratios' },
  { id: 'sectors',  label: 'Sectors' },
]

// All ratio rows from the four regime panels — used by the focused Ratios tab
// dropdown. Skip rows that are single-series (no numerator/denominator) since
// the Ratios tab is for ratios.
const ALL_ROWS: RegimeRow[] = REGIME_PANELS.flatMap((p) => p.rows)

export function Macro() {
  const { tab: tabParam } = useParams<{ tab?: string }>()
  const navigate = useNavigate()
  const tab: Tab = (TABS.find((t) => t.id === tabParam)?.id ?? 'overview') as Tab

  const [years, setYears] = useState<number>(5) // operator-locked default
  const since = useMemo(() => sinceFromYears(years), [years])

  const refresh = useMacroRefresh()

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
            <LineChartIcon className="h-5 w-5 text-muted-foreground" />
            Macro
            <InfoBubble term="regime" />
          </h2>
          <p className="text-muted-foreground text-sm">
            Regime context for per-ticker decisions. Twelve curated ratios + sector strip,
            updated nightly. <span className="text-muted-foreground/70">Click any row to expand its chart inline.</span>
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {/* Time-range chips */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground">Window</label>
            <ToggleGroup
              type="single"
              value={String(years)}
              onValueChange={(v) => v && setYears(Number(v))}
            >
              {TIME_RANGE_OPTIONS.map((o) => (
                <ToggleGroupItem
                  key={o.id}
                  value={String(o.years)}
                  variant="outline"
                  size="sm"
                  className="text-xs font-mono"
                >
                  {o.label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refresh.mutate(undefined)}
            disabled={refresh.isPending}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${refresh.isPending ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Sub-tabs */}
      <div
        role="tablist"
        aria-label="Macro view"
        className="inline-flex rounded-xl bg-background shadow-inset-sm p-1 gap-1"
      >
        {TABS.map((t) => {
          const active = t.id === tab
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={active}
              onClick={() => navigate(t.id === 'overview' ? '/macro' : `/macro/${t.id}`)}
              className={[
                'px-3 py-1.5 rounded-lg text-xs transition-all',
                active
                  ? 'bg-card text-foreground shadow-extruded-sm font-medium'
                  : 'text-muted-foreground hover:text-foreground',
              ].join(' ')}
            >
              {t.label}
            </button>
          )
        })}
      </div>

      {tab === 'overview' && <OverviewTab since={since} />}
      {tab === 'ratios' && <RatiosTab since={since} />}
      {tab === 'sectors' && <SectorStrip since={since} />}
    </div>
  )
}

function OverviewTab({ since }: { since: string }) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      {REGIME_PANELS.map((panel) => (
        <RegimePanel key={panel.title} panel={panel} since={since} />
      ))}
    </div>
  )
}

function RatiosTab({ since }: { since: string }) {
  // Filter to actual ratios (have numerator + denominator).
  const ratioRows = ALL_ROWS.filter((r): r is Extract<RegimeRow, { numerator: string }> =>
    'numerator' in r,
  )
  const [activeId, setActiveId] = useState(ratioRows[0]?.id ?? '')
  const active = ratioRows.find((r) => r.id === activeId) ?? ratioRows[0]

  const data = useMacroRatio({
    numerator: active.numerator,
    denominator: active.denominator,
    since,
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <label className="text-xs text-muted-foreground">Ratio</label>
        <select
          value={active.id}
          onChange={(e) => setActiveId(e.target.value)}
          className="bg-background rounded-xl px-3 py-2 text-sm shadow-inset-sm focus:outline-none focus:ring-2 focus:ring-violet"
        >
          {ratioRows.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label} ({r.numerator} / {r.denominator})
            </option>
          ))}
        </select>
      </div>

      {data.isLoading ? (
        <div className="rounded-2xl bg-background shadow-inset-sm p-12 text-center text-sm text-muted-foreground">
          Loading…
        </div>
      ) : (data.data?.points.length ?? 0) === 0 ? (
        <div className="rounded-2xl bg-background shadow-inset-sm p-12 text-center text-sm text-muted-foreground">
          No cached data — try Refresh above.
        </div>
      ) : (
        <RatioChart points={data.data!.points} height={420} />
      )}
    </div>
  )
}

// Re-export so the lazy import in App.tsx finds it.
export default Macro
