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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '../components/ui/toggle-group'
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

type Ohlc = { open?: number; high?: number; low?: number; close?: number; volume?: number }

// Side-by-side mini candles for "actual" vs "prediction". Sparse labels: 3
// non-adjacent reference points across the two candles (actual close, pred
// high, pred low) so the eye lands on anchors without clutter.
function MiniCandleCompare({ actual, predicted }: { actual: Ohlc | null; predicted: Ohlc | null }) {
  const vals = [actual?.high, actual?.low, predicted?.high, predicted?.low]
    .filter((v): v is number => typeof v === 'number')
  if (vals.length === 0) return <div className="text-[10px] text-muted-foreground">no data</div>
  const max = Math.max(...vals)
  const min = Math.min(...vals)
  const span = Math.max(max - min, 1e-6)
  const W = 160
  const H = 90
  const pad = 14
  const innerH = H - pad * 2
  const y = (v: number) => pad + (1 - (v - min) / span) * innerH
  const candle = (o: Ohlc | null, x: number, label: string) => {
    if (!o || o.open == null || o.high == null || o.low == null || o.close == null) {
      return (
        <g>
          <text x={x} y={H - 2} textAnchor="middle" fontSize="9" className="fill-muted-foreground">{label}</text>
        </g>
      )
    }
    const up = o.close >= o.open
    const fill = up ? 'fill-success' : 'fill-danger'
    const stroke = up ? 'stroke-success' : 'stroke-danger'
    const bodyTop = Math.min(y(o.open), y(o.close))
    const bodyBot = Math.max(y(o.open), y(o.close))
    const bodyH = Math.max(bodyBot - bodyTop, 1.5)
    return (
      <g>
        <line x1={x} x2={x} y1={y(o.high)} y2={y(o.low)} className={stroke} strokeWidth={1.2} />
        <rect x={x - 8} y={bodyTop} width={16} height={bodyH} className={fill} rx={1.5} />
        <text x={x} y={H - 2} textAnchor="middle" fontSize="9" className="fill-muted-foreground">{label}</text>
      </g>
    )
  }
  // 3 sparse refs: actual.close, predicted.high, predicted.low
  const refs: { v: number | undefined; x: number; y: number; anchor: 'start' | 'end'; label: string }[] = [
    { v: actual?.close, x: 36, y: actual?.close != null ? y(actual.close) : 0, anchor: 'end', label: actual?.close != null ? `$${actual.close.toFixed(2)}` : '' },
    { v: predicted?.high, x: W - 36, y: predicted?.high != null ? y(predicted.high) : 0, anchor: 'start', label: predicted?.high != null ? `H $${predicted.high.toFixed(2)}` : '' },
    { v: predicted?.low, x: W - 36, y: predicted?.low != null ? y(predicted.low) : 0, anchor: 'start', label: predicted?.low != null ? `L $${predicted.low.toFixed(2)}` : '' },
  ]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="font-mono">
      {candle(actual, 40, 'Actual')}
      {candle(predicted, W - 40, 'Predicted')}
      {refs.map((r, i) =>
        r.v == null ? null : (
          <text
            key={i}
            x={r.x}
            y={r.y + 3}
            textAnchor={r.anchor}
            fontSize="9"
            className="fill-foreground"
          >
            {r.label}
          </text>
        ),
      )}
    </svg>
  )
}
const FIELD_OPTIONS = ['open', 'high', 'low', 'close', 'volume'] as const
const DOW_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
type FieldKey = 'open' | 'high' | 'low' | 'close' | 'volume'
export function PredictionsByHorizon() {
  const [targetDate, setTargetDate] = useState(() => {
    // Predictions are forward-looking: a daily run made today targets tomorrow+ (T-1 onwards).
    // Default to tomorrow (UTC) so the user sees the run that fired last.
    const d = new Date()
    d.setUTCDate(d.getUTCDate() + 1)
    return d.toISOString().split('T')[0]
  })
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
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-heading font-semibold tracking-tight">
          Predictions by Horizon
        </h2>
        <p className="text-muted-foreground">
          Compare prediction accuracy across different time horizons.
        </p>
      </div>

      {/* Controls */}
      <Card>
        <CardContent className="p-6 space-y-5">
          <div className="grid gap-6 md:grid-cols-4">
            <div className="space-y-2">
              <Label>Target Date</Label>
              <Input
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                className="font-mono"
              />
            </div>

            <div className="space-y-2 md:col-span-2">
              <Label>Tickers (comma separated)</Label>
              <div className="space-y-1.5">
                <Input
                  value={tickers}
                  onChange={(e) => { setTickers(e.target.value); setTickersTouched(true) }}
                  className="font-mono uppercase"
                  placeholder="AAPL, MSFT, GOOGL"
                />
                {watchlist?.items && watchlist.items.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {watchlist.items.slice(0, 12).map((item) => (
                      <button
                        key={item.symbol}
                        type="button"
                        onClick={() => {
                          const current = tickers
                            .split(',')
                            .map((s) => s.trim().toUpperCase())
                            .filter(Boolean)
                          if (!current.includes(item.symbol)) {
                            setTickers([...current, item.symbol].join(','))
                            setTickersTouched(true)
                          }
                        }}
                        className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
                      >
                        +{item.symbol}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <Label>Horizons (days ago)</Label>
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
                <CardDescription>
                  Each cell: <span className="font-mono">Δ%</span> on{' '}
                  <span className="font-mono font-medium">{activeField}</span>{' '}
                  (top), actual close $ below — or predicted close $ in italics when the target date is still in the future.
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
                  <TableHead className="w-[100px]">Actual</TableHead>
                  {horizonsList.map((h) => (
                    <TableHead key={h} className="text-center min-w-[90px]">
                      T-{h}
                    </TableHead>
                  ))}
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
                        <TableCell className="text-muted-foreground font-mono">
                          —
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
                  const actualVal = getFieldValue(
                    tickerRows[0]?.actual as Record<string, number> | null,
                    activeField,
                  )
                  return (
                    <TableRow key={ticker}>
                      <TableCell className="font-mono font-bold sticky left-0 bg-card z-10">
                        {ticker}
                      </TableCell>
                      <TableCell className="font-mono text-sm">
                        {actualVal != null ? `$${actualVal.toFixed(2)}` : '—'}
                      </TableCell>
                      {horizonsList.map((h) => {
                        const row = tickerRows.find((r) => r.days_ago === h)
                        const predVal = getFieldValue(
                          row?.prediction as Record<string, number> | null,
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
                                  <div className="text-[10px] text-muted-foreground mb-1">
                                    {row?.ticker} · T-{h} · made {row?.made_on ?? '?'} · forecast only
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
                                <div className="text-[10px] text-muted-foreground mb-1">
                                  {row?.ticker} · T-{h} · made {row?.made_on ?? '?'}
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
      ) : (
        <div className="text-center py-12 text-sm text-muted-foreground rounded-2xl shadow-inset-sm flex flex-col items-center">
          <Grid3x3 className="h-8 w-8 mb-2 text-muted-foreground/50" />
          {predictions && tickersList.length > 0 ? (
            <>
              <p>No predictions for any of the selected tickers on {targetDate}.</p>
              <p className="text-xs mt-1 max-w-md">
                Predictions are generated by the daily scheduled run for whatever was on the watchlist <em>at run time</em>.
                If you added these symbols after the last run, hit <span className="font-medium">Fire Now</span> on the Schedule tab — predictions arrive in ~1 minute.
                Or pick an earlier <span className="font-medium">target date</span> covering symbols that were on the watchlist then.
              </p>
            </>
          ) : (
            <>
              <p>Configure parameters above to view the horizon matrix.</p>
              <p className="text-xs mt-1">Pick at least one ticker, one horizon (k-days-ago), and a target date.</p>
            </>
          )}
        </div>
      )}
    </div>
  )
}
