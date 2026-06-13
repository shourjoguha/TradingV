import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Button } from '../ui/button'
import { Skeleton } from '../ui/skeleton'
import {
  type AdminLoopRow,
  useAdminLoops,
  useUpdateCadence,
  useAdminSettings,
  useUpdateAdminSetting,
  useCostsMonthly,
} from '../../hooks/use-api'

/**
 * Loop → cost attribution. Anthropic charges accrue via Research stress-tests
 * (only loop with `cost_sensitive=true` on the cadenced side) and TV-context
 * vision summaries (HTTP-triggered on screenshot ingest, not a cadenced loop;
 * shown as a footnote rather than a per-loop row).
 *
 * If a new cost-sensitive loop is added, map its loop_id → driver here.
 */
type CostDriver = 'research' | 'vision' | 'none'
const LOOP_COST_DRIVER: Record<string, CostDriver> = {
  research_weekly: 'research',
}

function costForLoop(
  loopId: string,
  costsMonthly: { research_total_usd: number; vision_total_usd: number } | undefined,
): { usd: number; driver: CostDriver } {
  const driver = LOOP_COST_DRIVER[loopId] ?? 'none'
  if (!costsMonthly || driver === 'none') return { usd: 0, driver }
  const usd = driver === 'research' ? costsMonthly.research_total_usd : costsMonthly.vision_total_usd
  return { usd, driver }
}

function fmtCostCell(usd: number, driver: CostDriver): React.ReactNode {
  if (driver === 'none') {
    return <span className="text-muted-foreground tabular-nums">$0</span>
  }
  const dollars = usd >= 0.01 ? usd.toFixed(2) : usd.toFixed(3)
  return (
    <span className="tabular-nums">
      ${dollars}
      <span className="text-xs text-muted-foreground ml-1">/mo · {driver}</span>
    </span>
  )
}

const UNITS = [
  { id: 'seconds', label: 'sec', mul: 1 },
  { id: 'minutes', label: 'min', mul: 60 },
  { id: 'hours', label: 'hr', mul: 3600 },
  { id: 'days', label: 'day', mul: 86400 },
] as const
type UnitId = (typeof UNITS)[number]['id']

function pickUnit(seconds: number): UnitId {
  if (seconds % 86400 === 0 && seconds >= 86400) return 'days'
  if (seconds % 3600 === 0 && seconds >= 3600) return 'hours'
  if (seconds % 60 === 0 && seconds >= 60) return 'minutes'
  return 'seconds'
}

function CadenceEditor({ row }: { row: AdminLoopRow }) {
  const update = useUpdateCadence()
  const initialUnit = pickUnit(row.cadence_seconds)
  const initialMul = UNITS.find((u) => u.id === initialUnit)?.mul ?? 1
  const [unit, setUnit] = useState<UnitId>(initialUnit)
  const [value, setValue] = useState<number>(
    Math.round(row.cadence_seconds / initialMul),
  )
  const [enabled, setEnabled] = useState<boolean>(row.enabled)

  const dirty =
    value * (UNITS.find((u) => u.id === unit)?.mul ?? 1) !== row.cadence_seconds ||
    enabled !== row.enabled

  return (
    <div className="flex items-center gap-2 text-xs">
      <input
        type="number"
        min={1}
        value={value}
        onChange={(e) => setValue(Math.max(1, Number(e.target.value) || 1))}
        className="w-16 rounded border bg-background px-2 py-1"
      />
      <select
        value={unit}
        onChange={(e) => setUnit(e.target.value as UnitId)}
        className="rounded border bg-background px-2 py-1"
      >
        {UNITS.map((u) => (
          <option key={u.id} value={u.id}>{u.label}</option>
        ))}
      </select>
      <label className="flex items-center gap-1">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        enabled
      </label>
      <Button
        size="sm"
        variant="outline"
        disabled={!dirty || update.isPending}
        onClick={() => {
          const mul = UNITS.find((u) => u.id === unit)?.mul ?? 1
          update.mutate({
            loop_id: row.loop_id,
            cadence_seconds: value * mul,
            enabled,
          })
        }}
      >
        Save
      </Button>
    </div>
  )
}

function AnthropicKillSwitch() {
  const { data } = useAdminSettings()
  const update = useUpdateAdminSetting()
  if (!data) return null
  const enabled = data.items['anthropic.enabled']
  return (
    <div className="flex items-center justify-between rounded-md border p-3 text-sm">
      <div>
        <div className="font-medium">Anthropic API</div>
        <div className="text-xs text-muted-foreground">
          Master kill-switch for Research + TV vision Claude calls.
        </div>
      </div>
      <Button
        variant={enabled ? 'outline' : 'destructive'}
        size="sm"
        disabled={update.isPending}
        onClick={() =>
          update.mutate({ key: 'anthropic.enabled', value: !enabled })
        }
      >
        {enabled ? 'Enabled — disable' : 'Disabled — enable'}
      </Button>
    </div>
  )
}

export function CadencesTab() {
  const { data, isLoading } = useAdminLoops({ refetchMs: 30_000 })
  // MTD spend per cost driver (research / vision) — surfaced per-loop in the Cost column.
  const costs = useCostsMonthly()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Cadences</CardTitle>
        <CardDescription>
          Edit each loop's cadence and enabled flag. Writes to `app_settings`;
          next tick reads the new value. Cost column shows month-to-date spend
          attributed to the loop's cost driver — see <code className="text-xs">/admin/costs</code> for the per-day breakdown.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AnthropicKillSwitch />
        {isLoading && <Skeleton className="h-24 w-full" />}
        {data && (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b text-xs font-mono text-muted-foreground">
                  <th className="py-2 pr-3">Loop</th>
                  <th className="py-2 pr-3">Cadence</th>
                  <th className="py-2 pr-3 text-right">Cost (MTD)</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => {
                  const { usd, driver } = costForLoop(row.loop_id, costs.data)
                  return (
                    <tr key={row.loop_id} className="border-b last:border-b-0">
                      <td className="py-2 pr-3">
                        <div className="text-sm font-medium">{row.title}</div>
                        <div className="text-xs text-muted-foreground">
                          default: {row.default_cadence_seconds}s · loop_id: <code>{row.loop_id}</code>
                        </div>
                      </td>
                      <td className="py-2 pr-3">
                        <CadenceEditor row={row} />
                      </td>
                      <td className="py-2 pr-3 text-right text-xs">
                        {fmtCostCell(usd, driver)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="text-xs text-muted-foreground mt-3">
              <strong>TV-context vision cost</strong> (HTTP-triggered on screenshot ingest, not a cadenced loop):
              {costs.data ? <> ${costs.data.vision_total_usd.toFixed(2)} MTD across {costs.data.vision_count} calls.</> : <> loading...</>}{' '}
              Disable for the rest of the month via the Costs tab.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
