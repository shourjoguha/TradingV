import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '../components/ui/toggle-group'
import { useMacroRefresh } from '../hooks/use-api'
import {
  ChartBuilder,
  encodePanes,
  decodePanes,
  type PaneSpec,
  type AvailableSeries,
} from '../components/charts'
import { RegimePanel } from '../components/macro/RegimePanel'
import { SectorStrip } from '../components/macro/SectorStrip'
import { CyclePhaseWheel } from '../components/macro/CyclePhaseWheel'
import { RotationFootprintStrip } from '../components/macro/RotationFootprintStrip'
import { CorrelationHeatmap } from '../components/macro/CorrelationHeatmap'
import { RegimeConditionalBadges } from '../components/macro/RegimeConditionalBadges'
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
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
            <LineChartIcon className="h-5 w-5 text-muted-foreground" />
            Macro
            {/* Single canonical tooltip (2026-05-17 dedupe): the glossary
                `regime` entry defines what regime IS; the previous
                second tooltip ("12 curated ratios + sector strip, updated
                nightly. Click any row to expand…") was chrome describing
                page mechanics + a discoverable interaction. Dropped both
                — keep the only one that adds knowledge. */}
            <InfoBubble term="regime" />
          </h2>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {/* Time-range chips — 'Window' label dropped 2026-05-17
              (operator audit: redundant next to 1Y/3Y/5Y/10Y/Max buttons). */}
          <div className="flex items-center gap-2">
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
      {tab === 'sectors' && <SectorsTab since={since} />}
    </div>
  )
}

/**
 * Sectors sub-tab — dropdown-driven visualization selector + compact
 * sector grid + always-on drill-in chart at the bottom.
 *
 * 2026-05-17: operator opted to see ALL deferred viz options (rotation
 * footprint, regime-conditional badges, correlation heatmap) plus the
 * Phase Wheel, one at a time. The dropdown surfaces them; grid + chart
 * stay constant beneath so the operator can flip between perspectives
 * without losing context on the bottom panes.
 */
type SectorView = 'wheel' | 'rotation' | 'phaseConfirm' | 'correlation'

const SECTOR_VIEWS: Array<{ id: SectorView; label: string }> = [
  { id: 'wheel',        label: 'Cycle phase wheel' },
  { id: 'rotation',     label: 'Rotation footprint (12w)' },
  { id: 'phaseConfirm', label: 'Phase confirmation badges' },
  { id: 'correlation',  label: 'Correlation matrix (90d)' },
]

function SectorsTab({ since }: { since: string }) {
  const [view, setView] = useState<SectorView>('wheel')
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <label
          htmlFor="sector-view"
          className="text-xs font-mono text-muted-foreground shrink-0"
        >
          View
        </label>
        <select
          id="sector-view"
          value={view}
          onChange={(e) => setView(e.target.value as SectorView)}
          className="bg-background rounded-xl px-3 py-2 text-sm shadow-inset-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          {SECTOR_VIEWS.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
            </option>
          ))}
        </select>
      </div>
      {view === 'wheel' && <CyclePhaseWheel since={since} />}
      {view === 'rotation' && <RotationFootprintStrip since={since} />}
      {view === 'phaseConfirm' && <RegimeConditionalBadges since={since} />}
      {view === 'correlation' && <CorrelationHeatmap since={since} />}
      <SectorStrip since={since} />
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

/**
 * RatiosTab — multi-pane chart builder. Replaces the prior single-dropdown
 * single-chart view (2026-05-18 charts-enrichment). Operator can:
 *   - Add multiple ratios to the same pane (overlay)
 *   - Toggle chart type per pane (line / area / log-Y)
 *   - Add additional panes below (compare regimes)
 * Pane config persists to URL `?panes=…` for bookmark/share.
 *
 * `availableSeries` derived from the same `ALL_ROWS` registry the legacy
 * dropdown used — labels + numerator/denominator preserved verbatim.
 */
function RatiosTab({ since }: { since: string }) {
  const [searchParams, setSearchParams] = useSearchParams()

  const ratioRows = useMemo(
    () =>
      ALL_ROWS.filter(
        (r): r is Extract<RegimeRow, { numerator: string }> => 'numerator' in r,
      ),
    [],
  )

  const available = useMemo<AvailableSeries[]>(
    () =>
      ratioRows.map((r) => ({
        id: `${r.numerator}/${r.denominator}`,
        label: `${r.label} (${r.numerator} / ${r.denominator})`,
        build: () => ({
          kind: 'ratio',
          numerator: r.numerator,
          denominator: r.denominator,
          label: r.label,
        }),
      })),
    [ratioRows],
  )

  // Default = first ratio in a single line pane (preserves legacy default).
  const buildDefaultPanes = useCallback((): PaneSpec[] => {
    const first = ratioRows[0]
    if (!first) return []
    return [
      {
        id: `p_${Math.random().toString(36).slice(2, 8)}`,
        chartType: 'line',
        series: [
          {
            kind: 'ratio',
            id: `s_${Math.random().toString(36).slice(2, 8)}`,
            numerator: first.numerator,
            denominator: first.denominator,
            label: first.label,
          },
        ],
      },
    ]
  }, [ratioRows])

  // Initialize from URL on mount; thereafter local state drives URL.
  const [panes, setPanes] = useState<PaneSpec[]>(() => {
    const raw = searchParams.get('panes')
    const decoded = decodePanes(raw)
    return decoded.length > 0 ? decoded : buildDefaultPanes()
  })

  // Sync local → URL (compact encoding, elides defaults).
  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    const encoded = encodePanes(panes)
    // Don't pollute the URL when the user is in the default state.
    const isDefault =
      panes.length === 1 &&
      panes[0].chartType === 'line' &&
      panes[0].series.length === 1 &&
      panes[0].series[0].kind === 'ratio' &&
      panes[0].series[0].numerator === ratioRows[0]?.numerator &&
      panes[0].series[0].denominator === ratioRows[0]?.denominator
    if (isDefault) {
      next.delete('panes')
    } else {
      next.set('panes', encoded)
    }
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panes])

  return (
    <ChartBuilder
      panes={panes}
      onChange={setPanes}
      available={available}
      since={since}
    />
  )
}

// Re-export so the lazy import in App.tsx finds it.
export default Macro
