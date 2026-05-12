import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Button } from '../ui/button'
import { Skeleton } from '../ui/skeleton'
import { useBackend } from '../../hooks/use-backend'
import {
  type AdminLoopRow,
  useAdminLoops,
  useUpdateCadence,
  useAdminSettings,
  useUpdateAdminSetting,
} from '../../hooks/use-api'

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
  const { backendId } = useBackend()
  const { data, isLoading } = useAdminLoops({ refetchMs: 30_000 })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Cadences</CardTitle>
        <CardDescription>
          Edit each loop's cadence and enabled flag. Writes to `app_settings`;
          next tick reads the new value.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {backendId === 'railway' && (
          <div className="rounded-md border border-warning-fg/30 bg-warning-bg/30 px-3 py-2 text-xs text-warning-fg">
            Admin UI is laptop-local. Loops on Railway are gated by `INSTANCE_NAME` and don't read these settings.
          </div>
        )}
        <AnthropicKillSwitch />
        {isLoading && <Skeleton className="h-24 w-full" />}
        {data && (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Loop</th>
                  <th className="py-2 pr-3">Cadence</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.loop_id} className="border-b last:border-b-0">
                    <td className="py-2 pr-3">
                      <div className="text-sm font-medium">{row.title}</div>
                      <div className="text-[10px] text-muted-foreground">
                        default: {row.default_cadence_seconds}s
                      </div>
                    </td>
                    <td className="py-2 pr-3">
                      <CadenceEditor row={row} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
