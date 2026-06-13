/**
 * URL-state encode/decode for ChartBuilder.
 *
 * Compact text format chosen over base64-JSON for hackability + human-
 * readability. Schema (one pane per `;`, series w/in pane joined by `,`):
 *
 *   panes=ratio:XLK/SPY,ratio:XLE/SPY|type:line;ratio:HG/GC|type:area
 *
 * Series fragments:
 *   `ratio:NUM/DEN`         (label optional)
 *   `ratio:NUM/DEN:LABEL`   (label is URL-encoded)
 *   `series:SYM`
 *   `series:SYM:LABEL`
 *
 * Pane suffix `|type:<line|area|log>` is optional (defaults to line).
 *
 * Bounded by query-string sane size — ~2KB practical. The encoder elides
 * fragments that equal defaults to keep URLs short.
 */
import type { PaneSpec, SeriesSpec, ChartType } from './types'

function nextId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`
}

export function encodePanes(panes: PaneSpec[]): string {
  return panes
    .map((p) => {
      const seriesParts = p.series.map(encodeSeries).join(',')
      const typePart = p.chartType !== 'line' ? `|type:${p.chartType}` : ''
      return `${seriesParts}${typePart}`
    })
    .join(';')
}

function encodeSeries(s: SeriesSpec): string {
  if (s.kind === 'ratio') {
    const base = `ratio:${s.numerator}/${s.denominator}`
    return s.label ? `${base}:${encodeURIComponent(s.label)}` : base
  }
  const base = `series:${s.symbol}`
  return s.label ? `${base}:${encodeURIComponent(s.label)}` : base
}

export function decodePanes(raw: string | null | undefined): PaneSpec[] {
  if (!raw) return []
  return raw
    .split(';')
    .map((paneStr) => paneStr.trim())
    .filter(Boolean)
    .map((paneStr) => {
      const [seriesStr, ...rest] = paneStr.split('|')
      let chartType: ChartType = 'line'
      for (const segment of rest) {
        const [k, v] = segment.split(':')
        if (k === 'type' && (v === 'line' || v === 'area' || v === 'log')) {
          chartType = v
        }
      }
      const series = seriesStr
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map(decodeSeries)
        .filter((s): s is SeriesSpec => s !== null)
      return {
        id: nextId('p'),
        series,
        chartType,
      }
    })
    .filter((p) => p.series.length > 0)
}

function decodeSeries(s: string): SeriesSpec | null {
  // ratio:NUM/DEN[:LABEL]
  if (s.startsWith('ratio:')) {
    const rest = s.slice('ratio:'.length)
    const colonIdx = rest.indexOf(':')
    const head = colonIdx === -1 ? rest : rest.slice(0, colonIdx)
    const label = colonIdx === -1 ? undefined : decodeURIComponent(rest.slice(colonIdx + 1))
    const [num, den] = head.split('/')
    if (!num || !den) return null
    return { kind: 'ratio', id: nextId('s'), numerator: num, denominator: den, label }
  }
  // series:SYM[:LABEL]
  if (s.startsWith('series:')) {
    const rest = s.slice('series:'.length)
    const colonIdx = rest.indexOf(':')
    const sym = colonIdx === -1 ? rest : rest.slice(0, colonIdx)
    const label = colonIdx === -1 ? undefined : decodeURIComponent(rest.slice(colonIdx + 1))
    if (!sym) return null
    return { kind: 'series', id: nextId('s'), symbol: sym, label }
  }
  return null
}
