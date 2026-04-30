import React, { useEffect, useState, useRef } from 'react'
import { createChart, ColorType } from 'lightweight-charts'
import {
  usePredictionsByTarget,
  useWatchlist,
  useModels,
  useOhlcv,
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
import { EmptyState } from '../components/common'
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
import { TrendingUp } from 'lucide-react'
const FIELD_PRESETS = ['open', 'high', 'low', 'close', 'volume'] as const
const DOW_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
// Color palette for prediction lines by days_ago
// Prediction-line palette: anchored on neumorphic accent (violet)
// + secondary accent (teal), with neighborly variations. Keeps the
// chart inside the design system while still distinguishing N runs.
const PREDICTION_COLORS = [
  '#6C63FF', // violet (primary accent)
  '#38B2AC', // teal (secondary accent)
  '#8B84FF', // violet light
  '#5FAFA8', // success (also candle up)
  '#A78BFA', // muted violet
  '#4FD1C5', // muted teal
  '#7986CB', // indigo neighbor
  '#9F7AEA', // mid violet
  '#48BB78', // muted green
  '#06b6d4', // cyan neighbor
]
export function PredictionsByTarget() {
  const [ticker, setTicker] = useState('')
  const [tickerTouched, setTickerTouched] = useState(false)
  const [targetDate, setTargetDate] = useState(() => {
    const d = new Date()
    d.setUTCDate(d.getUTCDate() + 1)
    return d.toISOString().split('T')[0]
  })
  const [interval, setInterval] = useState('1d')
  const [modelId, setModelId] = useState('')
  const [fields, setFields] = useState<string[]>(['close'])
  const [madeOnDow, setMadeOnDow] = useState<string[]>([])
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const { data: watchlist } = useWatchlist({
    limit: 100,
  })
  const { data: models } = useModels()
  // Auto-pick first watchlist symbol on first load (until user picks one).
  useEffect(() => {
    if (tickerTouched) return
    const first = watchlist?.entries?.[0]?.symbol
    if (first && !ticker) setTicker(first)
  }, [watchlist, tickerTouched, ticker])
  const queryParams = {
    ticker,
    target_date: targetDate,
    interval,
    model_id: modelId && modelId !== '__all__' ? modelId : undefined,
    fields: fields.join(',') || undefined,
    made_on_dow: madeOnDow.length > 0 ? madeOnDow.join(',') : undefined,
  }
  const { data: predictions, isLoading } = usePredictionsByTarget(queryParams)
  const { data: ohlcvData } = useOhlcv({
    symbol: ticker,
    interval,
    limit: 60,
  })
  // Lightweight-charts rendering
  useEffect(() => {
    if (!chartContainerRef.current || !ohlcvData || ohlcvData.length === 0)
      return
    const container = chartContainerRef.current
    const chart = createChart(container, {
      layout: {
        background: {
          type: ColorType.Solid,
          color: '#E0E5EC',
        },
        textColor: '#3D4852',
        fontFamily: '"DM Sans", system-ui, sans-serif',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(163, 177, 198, 0.2)' },
        horzLines: { color: 'rgba(163, 177, 198, 0.2)' },
      },
      width: container.clientWidth,
      height: 320,
      crosshair: {
        vertLine: { color: 'rgba(108, 99, 255, 0.4)' },
        horzLine: { color: 'rgba(108, 99, 255, 0.4)' },
      },
      rightPriceScale: { borderColor: 'rgba(163, 177, 198, 0.4)' },
      timeScale: { borderColor: 'rgba(163, 177, 198, 0.4)' },
    })
    // Candlestick series — neumorphic-toned semantic colors so up/down
    // direction stays readable without breaking the cool-grey palette.
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#5FAFA8',
      downColor: '#E07A6F',
      borderUpColor: '#5FAFA8',
      borderDownColor: '#E07A6F',
      wickUpColor: '#5FAFA8',
      wickDownColor: '#E07A6F',
    })
    const candleData = ohlcvData
      .map((bar) => ({
        time: bar.time as string,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }))
      .sort((a, b) => (a.time < b.time ? -1 : 1))
    candleSeries.setData(candleData)
    // Add prediction lines color-coded by days_ago
    if (predictions?.predictions && predictions.predictions.length > 0) {
      const uniqueDaysAgo = [
        ...new Set(predictions.predictions.map((p) => p.days_ago)),
      ].sort((a, b) => a - b)
      uniqueDaysAgo.forEach((daysAgo, idx) => {
        const predsForDay = predictions.predictions
          .filter((p) => p.days_ago === daysAgo && p.close !== null)
          .sort((a, b) => (a.made_on < b.made_on ? -1 : 1))
        if (predsForDay.length === 0) return
        const color = PREDICTION_COLORS[idx % PREDICTION_COLORS.length]
        const lineSeries = chart.addLineSeries({
          color,
          lineWidth: 2,
          title: `T-${daysAgo}`,
          crosshairMarkerVisible: true,
          crosshairMarkerRadius: 3,
        })
        // Place prediction marker at the target date
        const lineData = predsForDay.map((p) => ({
          time: predictions.target_date as string,
          value: p.close!,
        }))
        // If we have the made_on date, show line from made_on to target_date
        if (predsForDay.length === 1) {
          const pred = predsForDay[0]
          lineSeries.setData([
            {
              time: pred.made_on as string,
              value: pred.close!,
            },
            {
              time: predictions.target_date as string,
              value: pred.close!,
            },
          ])
        } else {
          lineSeries.setData(lineData)
        }
      })
    }
    chart.timeScale().fitContent()
    const handleResize = () => {
      chart.applyOptions({
        width: container.clientWidth,
      })
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [ohlcvData, predictions])
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-heading font-semibold tracking-tight">
          Predictions by Target
        </h2>
        <p className="text-muted-foreground">
          View all predictions made for a specific target date.
        </p>
      </div>

      {/* Controls */}
      <Card>
        <CardContent className="p-6 space-y-5">
          <div className="grid gap-6 md:grid-cols-4">
            <div className="space-y-2">
              <Label>Ticker</Label>
              <Select value={ticker || undefined} onValueChange={(v) => { setTicker(v); setTickerTouched(true) }}>
                <SelectTrigger className="font-mono">
                  <SelectValue placeholder="Select ticker" />
                </SelectTrigger>
                <SelectContent>
                  {watchlist?.items.map((item) => (
                    <SelectItem key={item.symbol} value={item.symbol}>
                      {item.symbol}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Target Date</Label>
              <Input
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                className="font-mono"
              />
            </div>

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

          {/* Fields chips */}
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Fields</Label>
            <ToggleGroup
              type="multiple"
              value={fields}
              onValueChange={(v) => setFields(v.length > 0 ? v : ['close'])}
              className="justify-start"
            >
              {FIELD_PRESETS.map((f) => (
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

      {/* Chart */}
      {isLoading ? (
        <Card>
          <CardContent className="p-12 flex justify-center">
            <Skeleton className="h-[320px] w-full" />
          </CardContent>
        </Card>
      ) : predictions ? (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Actual vs Predicted</CardTitle>
                  <CardDescription className="mt-1">
                    Target:{' '}
                    <span className="font-mono">{predictions.target_date}</span>
                    {' | '}Actual Close:{' '}
                    <span className="font-mono font-bold">
                      {predictions.actual?.close
                        ? `$${predictions.actual.close.toFixed(2)}`
                        : '—'}
                    </span>
                    {!predictions.actual && (
                      <Badge variant="secondary" className="ml-2 text-[10px]">
                        Actual unavailable
                      </Badge>
                    )}
                  </CardDescription>
                </div>
                {predictions.predictions.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {[
                      ...new Set(
                        predictions.predictions.map((p) => p.days_ago),
                      ),
                    ]
                      .sort((a, b) => a - b)
                      .map((d, i) => (
                        <div
                          key={d}
                          className="flex items-center gap-1.5 text-xs text-muted-foreground"
                        >
                          <div
                            className="h-2 w-2 rounded-full"
                            style={{
                              backgroundColor:
                                PREDICTION_COLORS[i % PREDICTION_COLORS.length],
                            }}
                          />
                          <span className="font-mono">T-{d}</span>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div ref={chartContainerRef} className="w-full" />
            </CardContent>
          </Card>

          {/* Predictions Table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Prediction Details</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Made On</TableHead>
                    <TableHead>Days Ago</TableHead>
                    <TableHead>DOW</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead className="text-right">Open</TableHead>
                    <TableHead className="text-right">High</TableHead>
                    <TableHead className="text-right">Low</TableHead>
                    <TableHead className="text-right">Close</TableHead>
                    <TableHead className="text-right">Delta</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {predictions.predictions
                    .sort((a, b) => (a.made_on > b.made_on ? -1 : 1))
                    .map((pred, i) => {
                      const actualClose = predictions.actual?.close
                      const delta =
                        actualClose != null && pred.close != null
                          ? pred.close - actualClose
                          : null
                      const deltaPct =
                        actualClose && delta != null
                          ? (delta / actualClose) * 100
                          : null
                      return (
                        <TableRow key={`${pred.made_on}-${pred.model_id}-${i}`}>
                          <TableCell className="font-mono text-sm">
                            {pred.made_on}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className="font-mono text-xs"
                            >
                              T-{pred.days_ago}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {DOW_LABELS[pred.made_on_dow] ?? pred.made_on_dow}
                          </TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">
                            {pred.model_id}
                          </TableCell>
                          <TableCell className="text-right font-mono text-sm">
                            {pred.open != null
                              ? `$${pred.open.toFixed(2)}`
                              : '—'}
                          </TableCell>
                          <TableCell className="text-right font-mono text-sm">
                            {pred.high != null
                              ? `$${pred.high.toFixed(2)}`
                              : '—'}
                          </TableCell>
                          <TableCell className="text-right font-mono text-sm">
                            {pred.low != null ? `$${pred.low.toFixed(2)}` : '—'}
                          </TableCell>
                          <TableCell className="text-right font-mono text-sm font-medium">
                            {pred.close != null
                              ? `$${pred.close.toFixed(2)}`
                              : '—'}
                          </TableCell>
                          <TableCell className="text-right font-mono text-sm">
                            {deltaPct != null ? (
                              <span
                                className={
                                  deltaPct > 0
                                    ? 'text-red-500'
                                    : deltaPct < 0
                                      ? 'text-green-500'
                                      : 'text-muted-foreground'
                                }
                              >
                                {deltaPct > 0 ? '+' : ''}
                                {deltaPct.toFixed(2)}%
                              </span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                </TableBody>
              </Table>
              {predictions.predictions.length === 0 && (
                <div className="mt-4">
                  <EmptyState
                    icon={TrendingUp}
                    title={
                      <>
                        No predictions for <span className="font-mono font-medium">{ticker}</span> on {targetDate}.
                      </>
                    }
                    description={
                      <>
                        Predictions are generated by the daily scheduled run for symbols on the watchlist <em>at run time</em>.
                        {' '}If you added <span className="font-mono">{ticker}</span> after the last run, hit <span className="font-medium">Fire Now</span> on the Schedule tab — predictions will be available in ~1 minute.
                      </>
                    }
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      ) : (
        <EmptyState
          icon={TrendingUp}
          title="Select a ticker + target date above"
          description="Tickers come from your watchlist."
        />
      )}
    </div>
  )
}
