/**
 * ChartTimeControl — small toggle-group for per-chart time-period
 * selection. Sits in a chart's CardHeader to let the operator override
 * the page-level since/window for that one chart (e.g. rotation footprint
 * cadence + lookback, correlation matrix window).
 *
 * Generic over the preset id type — the chart wrapper defines its own
 * preset shape (e.g. `'12w' | '1y-monthly' | '5y-monthly'`).
 *
 * Lives at the charts/ root (not in /builder or /plotly) because it's
 * a UI control, not a chart primitive — but couples tightly to chart
 * configuration so charts/ is its natural home.
 */
import { ToggleGroup, ToggleGroupItem } from '../ui/toggle-group'

export interface TimePreset<Id extends string = string> {
  id: Id
  label: string
}

interface Props<Id extends string> {
  value: Id
  onChange: (id: Id) => void
  presets: TimePreset<Id>[]
  /** Optional aria-label. */
  ariaLabel?: string
}

export function ChartTimeControl<Id extends string>({
  value,
  onChange,
  presets,
  ariaLabel = 'Chart time range',
}: Props<Id>) {
  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(v) => v && onChange(v as Id)}
      aria-label={ariaLabel}
    >
      {presets.map((p) => (
        <ToggleGroupItem
          key={p.id}
          value={p.id}
          variant="outline"
          size="sm"
          className="text-xs font-mono"
        >
          {p.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}
