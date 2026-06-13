import React, { useEffect, useState } from 'react'
import {
  usePredictionsByHorizon,
  useWatchlist,
  useModels,
} from '../hooks/use-api'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '../components/ui/card'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { EmptyState, InfoBubble } from '../components/common'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '../components/ui/toggle-group'
import { DatePicker } from '../components/ui/date-picker'
import { MultiSelect } from '../components/ui/multi-select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import { Skeleton } from '../components/ui/skeleton'
import { Badge } from '../components/ui/badge'
import { Grid3x3 } from 'lucide-react'
import {
  MiniCandleCompare,
  type Ohlc,
} from '../components/charts/svg/MiniCandleCompare'

const FIELD_OPTIONS = ['open', 'high', 'low', 'close', 'volume'] as const
const DOW_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
type FieldKey = 'open' | 'high' | 'low' | 'close' | 'volume'
function intervalSuffix(interval: string): string {
  if (interval === '1h') return 'h'
  if (interval === '15m') return 'q' // 15-min quarters; rare in this view
  return 'd'
}
// Default anchor for /predictions/horizon. We back up two days from today
// (UTC) and skip weekends so the matrix lands on a session whose actual
// close has already printed for any operator running the daily scheduler.
//
// History:
//   • Original default = tomorrow → matrix was "predictions only" (no actuals).
//   • Then today (UTC) → still mostly empty since the day's bar isn't done.
//   • Now today − 2d, backed up over weekends → at least one column is
//     guaranteed to have actuals if the scheduler fired the prior weekday.
function defaultPredictionAnchor(): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - 2)
  // 0 = Sun, 6 = Sat. Back up to the most recent weekday so target_date hits
  // a real session bar (no weekend bars in equities, FX-spot is partial).
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6) {
    d.setUTCDate(d.getUTCDate() - 1)
  }
  return d.toISOString().split('T')[0]
}

export function PredictionsByHorizon() {
  const [targetDate, setTargetDate] = useState(defaultPredictionAnchor)
  const [horizons, setHorizons] = useState('1,2,3,4,5')
  const [tickers, setTickers] = useState('')
  const [tickersTouched, setTickersTouched] = useState(false)
  const [interval, setInterval] = useState('1d')
  const [modelId, setModelId] = useState('')
  const [activeField, setActiveField] = useState<FieldKey>('close')
  const [fields, setFields] = useState<string[]>(['close'])
  const [madeOnDow, setMadeOnDow] = useState<string[]>([])
  const { data: watchlist } = useWatchlist({
    limit: 100,
  })
  const { data: models } = useModels()
  // Auto-populate tickers from watchlist on first load (until user edits the field).
  useEffect(() => {
    if (tickersTouched) return
    if (!watchlist?.entries?.length) return
    setTickers(watchlist.entries.map((e: any) => e.symbol).join(','))
  }, [watchlist, tickersTouched])
  const queryParams = {
    target_date: targetDate,
    horizons,
    tickers,
    interval,
    model_id: modelId && modelId !== '__all__' ? modelId : undefined,
    // Always request OHLC so the hover tooltip can render full candles. The
    // active field chip still drives which value the cell's Δ% is derived
    // from — that's a presentation choice, not an API filter.
    fields: 'ohlc',
    made_on_dow: madeOnDow.length > 0 ? madeOnDow.join(',') : undefined,
    // Anchor mode: picked date is the day forecasts were made; each column's
    // target = anchor + horizon. Per-column actual lookup, so columns with
    // elapsed targets render colored Δ% while still-future columns render
    // hollow predicted-only — without forcing the operator to backdate the
    // picker. This matches the "show me my forecasts' progress" mental model.
    mode: 'anchor' as const,
  }
  const { data: predictions, isLoading } = usePredictionsByHorizon(queryParams)
  const horizonsList = horizons
    .split(',')
    .map((s) => Number(s.trim()))
    .filter((n) => !isNaN(n))
    .sort((a, b) => a - b)
  const tickersList = tickers
    .split(',')
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
  const getFieldValue = (
    obj: Record<string, number> | null | undefined,
    field: FieldKey,
  ): number | null => {
    if (!obj) return null
    const val = (obj as Record<string, number | undefined>)[field]
    return val != null ? val : null
  }
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-heading font-semibold tracking-tight">
          Predictions by Horizon
        </h2>
        <p className="text-muted-foreground">
          Pick the day forecasts were made (anchor). Each column is a forecast offset
          — target = anchor + N. Cells whose target has elapsed show actual + Δ%; still-future
          cells render hollow with predicted close only.
        </p>
      </div>

      {/* Controls */}
      <Card>
        <CardContent className="p-6 space-y-6">
          <div className="grid gap-6 md:grid-cols-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Label>Anchor (made-on)</Label>
                <button
                  type="button"
                  onClick={() => setTargetDate(defaultPredictionAnchor())}
                  className="text-xs font-mono text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
                  title="Reset to default anchor (today − 2 weekdays UTC) so the latest column has actuals to compare against. Use the date picker to pick a different anchor."
                >
                  Reset
                </button>
              </div>
              <DatePicker value={targetDate} onChange={setTargetDate} />
            </div>

            <div className="space-y-2 md:col-span-2">
              <Label>Tickers</Label>
              <MultiSelect
                options={(watchlist?.entries ?? []).map((e) => ({ value: e.symbol }))}
                value={tickersList}
                onChange={(next) => {
                  setTickers(next.join(','))
                  setTickersTouched(true)
                }}
                placeholder="Select tickers from your roster…"
                searchPlaceholder="Search tickers…"
              />
            </div>

            <div className="space-y-2">
              <Label>Horizons (days forward)</Label>
              <Input
                value={horizons}
                onChange={(e) => setHorizons(e.target.value)}
                className="font-mono"
                placeholder="1,2,3,4,5"
              />
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-4">
            <div className="space-y-2">
              <Label>Interval</Label>
              <Select value={interval} onValueChange={setInterval}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1d">1d</SelectItem>
                  <SelectItem value="1h">1h</SelectItem>
                  <SelectItem value="15m">15m</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Model</Label>
              <Select value={modelId || '__all__'} onValueChange={(v) => setModelId(v === '__all__' ? '' : v)}>
                <SelectTrigger>
                  <SelectValue placeholder="All models" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All Models</SelectItem>
                  {models?.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Field selector chips */}
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">
              Display Field
            </Label>
            <ToggleGroup
              type="single"
              value={activeField}
              onValueChange={(v) => {
                if (v) {
                  setActiveField(v as FieldKey)
                  setFields([v])
                }
              }}
              className="justify-start"
            >
              {FIELD_OPTIONS.map((f) => (
                <ToggleGroupItem
                  key={f}
                  value={f}
                  variant="outline"
                  size="sm"
                  className="font-mono text-xs"
                >
                  {f}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>

          {/* Made-on DOW chips */}
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">
              Made-on Day of Week
            </Label>
            <ToggleGroup
              type="multiple"
              value={madeOnDow}
              onValueChange={setMadeOnDow}
              className="justify-start"
            >
              {DOW_LABELS.map((label, idx) => (
                <ToggleGroupItem
                  key={idx}
                  value={String(idx)}
                  variant="outline"
                  size="sm"
                  className="text-xs"
                >
                  {label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
        </CardContent>
      </Card>

      {/* Matrix */}
      {isLoading ? (
        <Card>
          <CardContent className="p-12 flex justify-center">
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      ) : predictions && predictions.rows.some((r) => r.prediction) ? (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Horizon Matrix</CardTitle>
                <CardDescription className="inline-flex items-center gap-1 flex-wrap">
                  <span>Each cell: </span>
                  <span className="font-mono">Δ%</span>
                  <InfoBubble term="delta_pct" />
                  <span>on{' '}<span className="font-mono font-medium">{activeField}</span>{' '}(top), actual close $ below when target date elapsed; otherwise predicted close $ in italics with dashed border.</span>
                  Hover for an OHLC compare.
                  <span className="ml-2 text-green-500">■</span> undershoot
                  <span className="ml-1 text-red-500">■</span> overshoot
                  <span className="ml-1 text-muted-foreground">■</span> within ±1%
                </CardDescription>
              </div>
              <Badge variant="outline" className="font-mono text-xs">
                {tickersList.length} × {horizonsList.length}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[100px] sticky left-0 bg-card z-10">
                    Ticker
                  </TableHead>
                  {horizonsList.map((h) => {
                    // Column target = anchor + h (anchor mode). Format MM/DD
                    // for compact header. Anchor input is YYYY-MM-DD; parse
                    // as UTC to keep the date math timezone-stable.
                    const colTarget = (() => {
                      const [y, m, d] = targetDate.split('-').map(Number)
                      const dt = new Date(Date.UTC(y, (m || 1) - 1, d || 1))
                      dt.setUTCDate(dt.getUTCDate() + h)
                      return `${String(dt.getUTCMonth() + 1).padStart(2, '0')}/${String(dt.getUTCDate()).padStart(2, '0')}`
                    })()
                    return (
                      <TableHead key={h} className="text-center min-w-[110px]">
                        <div className="flex flex-col leading-tight">
                          <span className="font-mono">+{h}{intervalSuffix(interval)}</span>
                          <span className="text-xs font-mono text-muted-foreground">{colTarget}</span>
                        </div>
                      </TableHead>
                    )
                  })}
                </TableRow>
              </TableHeader>
              <TableBody>
                {tickersList.map((ticker) => {
                  const tickerRows = predictions.rows.filter(
                    (r) => r.ticker === ticker,
                  )
                  if (tickerRows.length === 0) {
                    return (
                      <TableRow key={ticker}>
                        <TableCell className="font-mono font-bold sticky left-0 bg-card">
                          {ticker}
                        </TableCell>
                        {horizonsList.map((h) => (
                          <TableCell
                            key={h}
                            className="text-center text-muted-foreground"
                          >
                            —
                          </TableCell>
                        ))}
                      </TableRow>
                    )
                  }
                  return (
                    <TableRow key={ticker}>
                      <TableCell className="font-mono font-bold sticky left-0 bg-card z-10">
                        {ticker}
                      </TableCell>
                      {horizonsList.map((h) => {
                        const row = tickerRows.find((r) => r.days_ago === h)
                        const predVal = getFieldValue(
                          row?.prediction as Record<string, number> | null,
                          activeField,
                        )
                        // Per-cell actual: in anchor mode each cell has its
                        // own target date, so each cell decides locally
                        // whether to render hollow (no actual) or filled.
                        const actualVal = getFieldValue(
                          row?.actual as Record<string, number> | null,
                          activeField,
                        )
                        if (predVal == null) {
                          return (
                            <TableCell
                              key={h}
                              className="text-center text-muted-foreground"
                            >
                              —
                            </TableCell>
                          )
                        }
                        const actualOhlc = (row?.actual as Ohlc | null) ?? null
                        const predOhlc = (row?.prediction as Ohlc | null) ?? null
                        if (actualVal == null) {
                          // Forward-looking: prediction exists but target date hasn't elapsed yet.
                          // Italic predicted close on a single horizontal line.
                          return (
                            <TableCell key={h} className="text-center p-0">
                              <div className="group relative w-full h-full px-3 py-4 font-mono flex flex-row items-baseline justify-center gap-2 text-muted-foreground bg-background shadow-inset-sm border border-dashed border-muted-foreground/20">
                                <span className="text-base font-semibold leading-none">→</span>
                                <span className="text-sm italic tabular-nums opacity-90">${predVal.toFixed(2)}</span>
                                <div className="invisible group-hover:visible absolute z-30 top-full left-1/2 -translate-x-1/2 mt-1 p-2 rounded-xl bg-card shadow-extruded text-left pointer-events-none">
                                  <div className="text-xs text-muted-foreground mb-1">
                                    {row?.ticker} · +{h}{intervalSuffix(interval)} · target {row?.target_date ?? '?'} · forecast only
                                  </div>
                                  <MiniCandleCompare actual={null} predicted={predOhlc} />
                                </div>
                              </div>
                            </TableCell>
                          )
                        }
                        const deltaPct =
                          ((predVal - actualVal) / actualVal) * 100
                        const colorClass =
                          deltaPct > 1
                            ? 'text-danger bg-danger-bg'
                            : deltaPct < -1
                              ? 'text-success bg-success-bg'
                              : 'text-muted-foreground bg-background shadow-inset-sm'
                        return (
                          <TableCell key={h} className="text-center p-0">
                            <div
                              className={`group relative w-full h-full px-3 py-4 font-mono flex flex-row items-baseline justify-center gap-2 ${colorClass}`}
                            >
                              <span className="text-base font-semibold tabular-nums leading-none">
                                {deltaPct > 0 ? '+' : ''}
                                {deltaPct.toFixed(1)}%
                              </span>
                              <span className="text-sm tabular-nums opacity-90">
                                ${actualVal.toFixed(2)}
                              </span>
                              <div className="invisible group-hover:visible absolute z-30 top-full left-1/2 -translate-x-1/2 mt-1 p-2 rounded-xl bg-card shadow-extruded text-left pointer-events-none">
                                <div className="text-xs text-muted-foreground mb-1">
                                  {row?.ticker} · +{h}{intervalSuffix(interval)} · target {row?.target_date ?? '?'}
                                </div>
                                <MiniCandleCompare actual={actualOhlc} predicted={predOhlc} />
                              </div>
                            </div>
                          </TableCell>
                        )
                      })}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : predictions && tickersList.length > 0 ? (
        <EmptyState
          icon={Grid3x3}
          title={`No predictions for the selected tickers on ${targetDate}.`}
          description={
            <>
              Predictions are generated by the daily scheduled run for whatever was on the watchlist <em>at run time</em>.
              {' '}If you added these symbols after the last run, hit <span className="font-medium">Fire Now</span> on the Schedule tab — predictions arrive in ~1 minute.
              {' '}Or pick an earlier <span className="font-medium">target date</span> covering symbols that were on the watchlist then.
            </>
          }
        />
      ) : (
        <EmptyState
          icon={Grid3x3}
          title="Configure parameters above to view the horizon matrix"
          description="Pick at least one ticker, one horizon (k-days-ago), and a target date."
        />
      )}
    </div>
  )
}
