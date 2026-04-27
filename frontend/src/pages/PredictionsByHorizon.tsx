import React, { useState } from 'react'
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
const FIELD_OPTIONS = ['open', 'high', 'low', 'close', 'volume'] as const
const DOW_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
type FieldKey = 'open' | 'high' | 'low' | 'close' | 'volume'
export function PredictionsByHorizon() {
  const [targetDate, setTargetDate] = useState(
    new Date().toISOString().split('T')[0],
  )
  const [horizons, setHorizons] = useState('1,2,3,4,5')
  const [tickers, setTickers] = useState('AAPL,MSFT,GOOGL')
  const [interval, setInterval] = useState('1d')
  const [modelId, setModelId] = useState('')
  const [activeField, setActiveField] = useState<FieldKey>('close')
  const [fields, setFields] = useState<string[]>(['close'])
  const [madeOnDow, setMadeOnDow] = useState<string[]>([])
  const { data: watchlist } = useWatchlist({
    limit: 100,
  })
  const { data: models } = useModels()
  const queryParams = {
    target_date: targetDate,
    horizons,
    tickers,
    interval,
    model_id: modelId || undefined,
    fields: fields.join(',') || undefined,
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
                  onChange={(e) => setTickers(e.target.value)}
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
              <Select value={modelId} onValueChange={setModelId}>
                <SelectTrigger>
                  <SelectValue placeholder="All models" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All Models</SelectItem>
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
      ) : predictions ? (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Horizon Matrix</CardTitle>
                <CardDescription>
                  Delta % between predicted{' '}
                  <span className="font-mono font-medium">{activeField}</span>{' '}
                  and actual.
                  <span className="ml-2 text-green-500">■</span> undershoot
                  <span className="ml-2 text-red-500">■</span> overshoot
                  <span className="ml-2 text-muted-foreground">■</span> within
                  ±1%
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
                        if (actualVal == null || predVal == null) {
                          return (
                            <TableCell
                              key={h}
                              className="text-center text-muted-foreground"
                            >
                              —
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
                              className={`w-full h-full p-3 font-mono text-xs flex flex-col items-center justify-center ${colorClass}`}
                            >
                              <div className="font-medium">
                                {deltaPct > 0 ? '+' : ''}
                                {deltaPct.toFixed(2)}%
                              </div>
                              <div className="text-[10px] opacity-60 mt-0.5">
                                ${predVal.toFixed(2)}
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
          <p>Configure parameters above to view the horizon matrix.</p>
          <p className="text-xs mt-1">Pick at least one ticker, one horizon (k-days-ago), and a target date.</p>
        </div>
      )}
    </div>
  )
}
