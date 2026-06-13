/**
 * CorrelationHeatmap — 9×9 pairwise Pearson correlation of daily log-returns
 * over the last 90 trading days. Tier-2 chart (Plotly Heatmap) since the
 * Sectors viz is an expanded panel; we want the free hover/zoom/colorbar.
 *
 * Rewritten 2026-05-17 (Phase 5 of charts-plotly migration): data-only
 * domain wrapper now; rendering delegated to `<Heatmap>` from the shared
 * chart infra. Previously: HTML <table> w/ inline-style cells + bespoke
 * `corrColor()` + `corrFg()` (now removed; colors come from the
 * `CORRELATION_GRADIENT` palette token).
 */
import { useMemo, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { InfoBubble } from '../common'
import { Heatmap } from '../charts/plotly/Heatmap'
import { LineChart } from '../charts/plotly/LineChart'
import { ChartTimeControl, type TimePreset } from '../charts/ChartTimeControl'
import { useMacroSeries } from '../../hooks/use-api'
import { SECTOR_ETFS } from '../../lib/macro-views'
import { correlationMatrix, rollingPairCorrelation } from '../../lib/sector-strength'
import type { MacroPoint } from '../../lib/types'
import { X } from 'lucide-react'

interface Props {
  since: string
}

/**
 * Correlation window presets (trading days). Both the heatmap and the
 * rolling-pair drill-in below use the selected window — operator picks
 * once, both views cascade.
 *
 * Data ceiling is the page-level `since` chip — `correlationMatrix` clamps
 * window to available data via `pts.slice(-window-1)`, so picking 5y here
 * with the page set to 1Y just uses 1Y silently.
 */
type WindowId = '30d' | '90d' | '180d' | '1y' | '3y' | '5y'
const WINDOW_PRESETS: Array<TimePreset<WindowId> & { days: number }> = [
  { id: '30d',  label: '30d',  days: 30 },
  { id: '90d',  label: '90d',  days: 90 },
  { id: '180d', label: '180d', days: 180 },
  { id: '1y',   label: '1y',   days: 252 },
  { id: '3y',   label: '3y',   days: 756 },
  { id: '5y',   label: '5y',   days: 1260 },
]

export function CorrelationHeatmap({ since }: Props) {
  const [windowId, setWindowId] = useState<WindowId>('90d')
  const windowDays = WINDOW_PRESETS.find((w) => w.id === windowId)?.days ?? 90

  const xlk = useMacroSeries({ symbol: 'XLK', since })
  const xlf = useMacroSeries({ symbol: 'XLF', since })
  const xle = useMacroSeries({ symbol: 'XLE', since })
  const xlv = useMacroSeries({ symbol: 'XLV', since })
  const xli = useMacroSeries({ symbol: 'XLI', since })
  const xlp = useMacroSeries({ symbol: 'XLP', since })
  const xly = useMacroSeries({ symbol: 'XLY', since })
  const xlu = useMacroSeries({ symbol: 'XLU', since })
  const xlb = useMacroSeries({ symbol: 'XLB', since })

  const closesBySymbol = useMemo<Record<string, MacroPoint[]>>(
    () => ({
      XLK: xlk.data?.points ?? [],
      XLF: xlf.data?.points ?? [],
      XLE: xle.data?.points ?? [],
      XLV: xlv.data?.points ?? [],
      XLI: xli.data?.points ?? [],
      XLP: xlp.data?.points ?? [],
      XLY: xly.data?.points ?? [],
      XLU: xlu.data?.points ?? [],
      XLB: xlb.data?.points ?? [],
    }),
    [
      xlk.data, xlf.data, xle.data, xlv.data, xli.data,
      xlp.data, xly.data, xlu.data, xlb.data,
    ],
  )

  const matrix = useMemo(
    () => correlationMatrix(closesBySymbol, windowDays),
    [closesBySymbol, windowDays],
  )

  const symbols = SECTOR_ETFS.map((s) => s.symbol)
  const empty = symbols.every((s) => (closesBySymbol[s]?.length ?? 0) === 0)

  // Drill-in: clicking a cell selects a pair → rolling 90d Pearson rendered below.
  const [selectedPair, setSelectedPair] = useState<{ a: string; b: string } | null>(null)
  const rollingPoints = useMemo<MacroPoint[]>(() => {
    if (!selectedPair) return []
    const a = closesBySymbol[selectedPair.a] ?? []
    const b = closesBySymbol[selectedPair.b] ?? []
    return rollingPairCorrelation(a, b, windowDays)
  }, [selectedPair, closesBySymbol, windowDays])

  // Shape `matrix` (Record<row, Record<col, number>>) into the row-major
  // z-grid Plotly expects.
  const z = useMemo(
    () =>
      symbols.map((row) =>
        symbols.map((col) => {
          const v = matrix[row]?.[col]
          return Number.isFinite(v) ? v : NaN
        }),
      ),
    [matrix, symbols],
  )

  // Compute average off-diagonal correlation as a regime-cohesion summary.
  const avgOffDiag = useMemo(() => {
    let sum = 0
    let n = 0
    for (let i = 0; i < symbols.length; i++) {
      for (let j = 0; j < symbols.length; j++) {
        if (i === j) continue
        const v = z[i]?.[j]
        if (Number.isFinite(v)) {
          sum += v
          n += 1
        }
      }
    }
    return n > 0 ? sum / n : null
  }, [z, symbols])

  return (
    <Card className="relative">
      <div
        aria-hidden
        className="absolute left-0 top-0 bottom-0 w-1 rounded-l-3xl bg-identity-narrative"
      />
      <CardHeader className="pb-1 md:pb-1">
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <CardTitle className="text-xl flex items-center gap-2">
            Correlation matrix
            <InfoBubble
              label="About the Correlation Matrix"
              content={
                <>
                  Pearson correlation of daily log-returns between each
                  pair of sectors over the selected window. Green = move
                  together, red = move opposite, grey = uncorrelated.
                  Read: high average correlation (lots of green) = regime
                  cohesion (sectors trading like one instrument). Click a
                  cell to see the rolling-pair correlation over time.
                  Short windows = recent cohesion; long windows = secular
                  / business-cycle cohesion. Data ceiling is the
                  page-level time chip.
                </>
              }
            />
          </CardTitle>
          <ChartTimeControl
            value={windowId}
            onChange={setWindowId}
            presets={WINDOW_PRESETS}
            ariaLabel="Correlation window"
          />
        </div>
      </CardHeader>
      <CardContent>
        {empty ? (
          <div className="text-xs text-muted-foreground italic p-4 text-center">
            Need at least 90 days of cached daily closes.
          </div>
        ) : (
          <div className="space-y-3">
            {avgOffDiag != null && (
              <div className="text-xs text-muted-foreground">
                {windowDays}-day window · average off-diagonal correlation:{' '}
                <span className="font-mono font-semibold text-foreground tabular-nums">
                  {avgOffDiag >= 0 ? '+' : ''}
                  {avgOffDiag.toFixed(2)}
                </span>
                {' · '}
                {avgOffDiag > 0.7
                  ? 'tight cohesion'
                  : avgOffDiag > 0.4
                    ? 'moderate'
                    : 'dispersed'}
              </div>
            )}
            <Heatmap
              rows={symbols}
              cols={symbols}
              z={z}
              height={380}
              onCellClick={(a, b) => {
                if (a === b) return // ignore diagonal
                setSelectedPair({ a, b })
              }}
            />
            {selectedPair && (
              <div className="space-y-2 mt-2 rounded-2xl bg-background shadow-inset-sm p-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs text-muted-foreground">
                    Rolling {windowDays}-day Pearson correlation:{' '}
                    <span className="font-mono font-semibold text-foreground">
                      {selectedPair.a} vs {selectedPair.b}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedPair(null)}
                    className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-card"
                    aria-label="Clear pair selection"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
                {rollingPoints.length === 0 ? (
                  <div className="text-xs text-muted-foreground italic py-6 text-center">
                    Need at least 91 days of overlapping history for both
                    series. Try a wider time window.
                  </div>
                ) : (
                  <LineChart points={rollingPoints} height={200} />
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
