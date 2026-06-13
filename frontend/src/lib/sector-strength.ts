/**
 * Sector relative-strength derivations powering the RS Leadership Ladder.
 *
 * Pure functions only — no React, no fetching. Input: a sector's
 * `MacroPoint[]` ratio series (already `sector_close / SPY_close` from
 * `/v1/macro/ratio`). Output: indexed RS series, current rank, momentum,
 * z-score series for sparkline shape, and a "defensive crowding" flag.
 *
 * Math contract (2026-05-17 council pick — see
 * `~/.claude/plans/now-when-i-use-radiant-yao.md`):
 *
 *   RS(sector, t)         = ratio.value(t)   (already sector/SPY from backend)
 *   RS-indexed(sector, t) = 100 × RS(t) / RS(t - LOOKBACK_BASE)
 *   RS-rank(t)            = argsort_desc(RS-indexed) across the 9 sectors
 *   RS-momentum(sector,t) = RS(t) / RS(t - MOMENTUM_WINDOW) - 1
 *   RS-zscore(sector,t)   = (RS(t) - μ_126d) / σ_126d   (rolling)
 *
 * All Close-only. No new backend endpoint. Reuses the existing
 * `useMacroRatio` cache w/ 5-min stale time (one query per sector).
 */
import type { MacroPoint } from './types'
import {
  RS_LOOKBACK_BASE,
  RS_MOMENTUM_THRESHOLD,
  RS_MOMENTUM_WINDOW,
  RS_ZSCORE_WINDOW,
  SECTOR_ETFS,
} from './macro-views'

/**
 * Most-recent ratio value, or null when empty / non-finite.
 */
export function latestValue(points: MacroPoint[]): number | null {
  if (points.length === 0) return null
  const v = points[points.length - 1].value
  return Number.isFinite(v) ? v : null
}

/**
 * `RS-indexed` at the latest point — normalized so that 1y ago = 100.
 * Returns null if the series has fewer than `lookback + 1` points (need
 * one historical point + one current point) or the lookback value is
 * non-finite / zero (avoids divide-by-zero).
 *
 * Note: lookback is interpreted as **trading days from the tail** — series
 * is daily Close so 252 indices ≈ 1 trading year. Weekly resampling is
 * NOT applied here (caller already gets daily data from the backend).
 */
export function rsIndexed(
  points: MacroPoint[],
  lookback: number = RS_LOOKBACK_BASE,
): number | null {
  if (points.length < lookback + 1) return null
  const last = points[points.length - 1].value
  const base = points[points.length - 1 - lookback].value
  if (!Number.isFinite(base) || base === 0) return null
  return 100 * (last / base)
}

/**
 * Short-term rate-of-change of the raw RS series — used as the chevron
 * direction on each ladder card. Returns null when insufficient history.
 *
 * Output is unitless (e.g. 0.012 = +1.2% over the window).
 */
export function rsMomentum(
  points: MacroPoint[],
  window: number = RS_MOMENTUM_WINDOW,
): number | null {
  if (points.length < window + 1) return null
  const last = points[points.length - 1].value
  const prev = points[points.length - 1 - window].value
  if (!Number.isFinite(prev) || prev === 0) return null
  return last / prev - 1
}

/**
 * Chevron direction string for `rsMomentum`. Symmetric ±threshold dead
 * zone produces a neutral `→` so noise doesn't flip operator's read
 * every refresh.
 */
export type MomentumDir = 'up' | 'down' | 'flat'

export function momentumDir(
  mom: number | null,
  threshold: number = RS_MOMENTUM_THRESHOLD,
): MomentumDir {
  if (mom == null) return 'flat'
  if (mom > threshold) return 'up'
  if (mom < -threshold) return 'down'
  return 'flat'
}

/**
 * Rolling z-score series — feeds the per-card sparkline so the operator
 * sees how the sector's RS is currently positioned vs its own recent
 * distribution (not absolute price level). The resulting series is
 * dimensionless and centered on 0; same `MacroPoint[]` shape so the
 * existing `<Sparkline>` primitive renders it without modification.
 *
 * The first `window` points carry no z-score (insufficient history) and
 * are emitted as `value: 0` placeholders so the sparkline still has a
 * full axis — alternative would be to slice, but that misaligns the time
 * axis across cards.
 */
export function rsZScoreSeries(
  points: MacroPoint[],
  window: number = RS_ZSCORE_WINDOW,
): MacroPoint[] {
  if (points.length === 0) return []
  const out: MacroPoint[] = []
  for (let i = 0; i < points.length; i++) {
    if (i < window) {
      out.push({ ts: points[i].ts, value: 0 })
      continue
    }
    const slice = points.slice(i - window + 1, i + 1)
    const n = slice.length
    let sum = 0
    for (const p of slice) sum += p.value
    const mean = sum / n
    let sq = 0
    for (const p of slice) sq += (p.value - mean) ** 2
    const variance = sq / n
    const std = Math.sqrt(variance)
    const z = std > 0 ? (points[i].value - mean) / std : 0
    out.push({ ts: points[i].ts, value: z })
  }
  return out
}

/**
 * Cross-sectional descending rank of a sector against a peer set on the
 * `rsIndexed` axis. `1` = strongest, `n` = weakest. Sectors with null
 * `rsIndexed` (insufficient history) sort to the bottom and receive
 * `null` rank — so the UI can render them as "—" without altering peers'
 * rank positions.
 */
export function rsRankBySymbol(
  series: Record<string, MacroPoint[]>,
  lookback: number = RS_LOOKBACK_BASE,
): Record<string, number | null> {
  const indexed: Array<{ symbol: string; rs: number | null }> = Object.keys(
    series,
  ).map((symbol) => ({ symbol, rs: rsIndexed(series[symbol], lookback) }))
  const sortable = indexed
    .filter((x): x is { symbol: string; rs: number } => x.rs != null)
    .sort((a, b) => b.rs - a.rs)
  const out: Record<string, number | null> = {}
  for (const x of indexed) out[x.symbol] = null
  sortable.forEach((x, i) => {
    out[x.symbol] = i + 1
  })
  return out
}

/**
 * Weekly rotation footprint — for each of the last N weeks, take a
 * snapshot of which sectors held the top `topK` RS ranks. Used by the
 * RotationFootprintStrip viz so the operator can scan left→right and see
 * leadership rotate (or persist) over time.
 *
 * Implementation: weekly snapshots are taken at every Friday-equivalent
 * (every ~5 daily points from the tail). For each snapshot timestamp t,
 * trim each sector's series to [0, t] and run `rsRankBySymbol`, then
 * record the top-K. Cheap: 12 weeks × 9 sectors × O(N) indexed lookups.
 */
export interface RotationSnapshot {
  /** ISO date of the snapshot's last data point. */
  weekEnding: string
  /** Symbols in top-K order (1 = strongest). May be shorter than topK
   *  if insufficient data. */
  topK: string[]
}

/**
 * Per-week rank matrix for ALL symbols (not just top-K). Used by the
 * bump-chart redesign of the rotation footprint — the bump chart needs the
 * full 9-sector rank curve over time, not the truncated top-3 per week.
 *
 * Same weekly cadence as `weeklyRotationFootprint`. Output:
 *   `Array<{ weekEnding, ranks: Record<sym, number | null> }>` where `ranks[sym]`
 *   is 1 (strongest) … N (weakest) at that week's close, or `null` if
 *   insufficient history to index.
 */
export interface WeeklyRanks {
  weekEnding: string
  ranks: Record<string, number | null>
}
export function weeklyRankMatrix(
  seriesBySymbol: Record<string, MacroPoint[]>,
  weeks: number = 12,
  daysPerWeek: number = 5,
): WeeklyRanks[] {
  const symbols = Object.keys(seriesBySymbol)
  if (symbols.length === 0) return []
  const refTimeline = seriesBySymbol[symbols[0]] ?? []
  if (refTimeline.length === 0) return []
  const out: WeeklyRanks[] = []
  for (let w = weeks - 1; w >= 0; w--) {
    const endIdx = refTimeline.length - 1 - w * daysPerWeek
    if (endIdx < RS_LOOKBACK_BASE) continue
    const sliced: Record<string, MacroPoint[]> = {}
    for (const sym of symbols) {
      sliced[sym] = seriesBySymbol[sym].slice(0, endIdx + 1)
    }
    const ranks = rsRankBySymbol(sliced)
    out.push({ weekEnding: refTimeline[endIdx].ts, ranks })
  }
  return out
}

/**
 * Rolling Pearson correlation between two series. For each day `t`,
 * computes Pearson on the trailing `window` daily log-returns of A and B.
 * Returns `Array<{ ts, value }>` aligned to the shorter input series's
 * timestamps. Used by the CorrelationHeatmap click-cell drill-in.
 *
 * Inputs should be raw closes (same as `correlationMatrix`).
 */
export function rollingPairCorrelation(
  a: MacroPoint[],
  b: MacroPoint[],
  window: number = 90,
): MacroPoint[] {
  if (a.length < window + 1 || b.length < window + 1) return []
  // Align by timestamp.
  const byTsA = new Map(a.map((p) => [p.ts, p.value]))
  const aligned: Array<{ ts: string; va: number; vb: number }> = []
  for (const p of b) {
    const va = byTsA.get(p.ts)
    if (va != null && p.value != null) {
      aligned.push({ ts: p.ts, va, vb: p.value })
    }
  }
  if (aligned.length < window + 1) return []
  // Pre-compute log-returns.
  const rets: Array<{ ts: string; ra: number; rb: number }> = []
  for (let i = 1; i < aligned.length; i++) {
    const ra = Math.log(aligned[i].va / aligned[i - 1].va)
    const rb = Math.log(aligned[i].vb / aligned[i - 1].vb)
    if (Number.isFinite(ra) && Number.isFinite(rb)) {
      rets.push({ ts: aligned[i].ts, ra, rb })
    }
  }
  if (rets.length < window) return []
  const out: MacroPoint[] = []
  for (let i = window - 1; i < rets.length; i++) {
    const slice = rets.slice(i - window + 1, i + 1)
    const n = slice.length
    let sa = 0, sb = 0
    for (const r of slice) { sa += r.ra; sb += r.rb }
    const ma = sa / n, mb = sb / n
    let cov = 0, va = 0, vb = 0
    for (const r of slice) {
      const da = r.ra - ma, db = r.rb - mb
      cov += da * db
      va += da * da
      vb += db * db
    }
    const denom = Math.sqrt(va * vb)
    const corr = denom > 0 ? cov / denom : 0
    out.push({ ts: rets[i].ts, value: corr })
  }
  return out
}

export function weeklyRotationFootprint(
  seriesBySymbol: Record<string, MacroPoint[]>,
  weeks: number = 12,
  topK: number = 3,
  daysPerWeek: number = 5,
): RotationSnapshot[] {
  const symbols = Object.keys(seriesBySymbol)
  if (symbols.length === 0) return []
  // Use the first symbol's series as the timeline reference (all 9 share
  // the same backend timestamps after the ratio join, so any will do).
  const refTimeline = seriesBySymbol[symbols[0]] ?? []
  if (refTimeline.length === 0) return []
  const out: RotationSnapshot[] = []
  // Walk back from the tail in weekly increments.
  for (let w = weeks - 1; w >= 0; w--) {
    const endIdx = refTimeline.length - 1 - w * daysPerWeek
    if (endIdx < RS_LOOKBACK_BASE) continue // need full lookback for indexing
    const sliced: Record<string, MacroPoint[]> = {}
    for (const sym of symbols) {
      sliced[sym] = seriesBySymbol[sym].slice(0, endIdx + 1)
    }
    const ranks = rsRankBySymbol(sliced)
    const sorted = symbols
      .map((s) => ({ s, r: ranks[s] }))
      .filter((x): x is { s: string; r: number } => x.r != null)
      .sort((a, b) => a.r - b.r)
      .slice(0, topK)
      .map((x) => x.s)
    out.push({
      weekEnding: refTimeline[endIdx].ts,
      topK: sorted,
    })
  }
  return out
}

/**
 * Pairwise Pearson correlation matrix of daily log-returns over the last
 * `window` trading days. Returns a `Record<symA, Record<symB, number>>`
 * with values in [-1, +1]; diagonal is always 1.
 *
 * Input series should be raw closes (the matrix is computed on returns,
 * not ratios — co-movement of price changes is what operator wants to
 * read when asking "which sectors move together?").
 */
export function correlationMatrix(
  seriesBySymbol: Record<string, MacroPoint[]>,
  window: number = 90,
): Record<string, Record<string, number>> {
  const symbols = Object.keys(seriesBySymbol)
  const returns: Record<string, number[]> = {}
  for (const sym of symbols) {
    const pts = seriesBySymbol[sym] ?? []
    const slice = pts.slice(-window - 1)
    const rs: number[] = []
    for (let i = 1; i < slice.length; i++) {
      const prev = slice[i - 1].value
      const cur = slice[i].value
      if (Number.isFinite(prev) && prev > 0 && Number.isFinite(cur) && cur > 0) {
        rs.push(Math.log(cur / prev))
      } else {
        rs.push(0)
      }
    }
    returns[sym] = rs
  }
  function pearson(a: number[], b: number[]): number {
    const n = Math.min(a.length, b.length)
    if (n === 0) return 0
    let sa = 0, sb = 0
    for (let i = 0; i < n; i++) {
      sa += a[i]
      sb += b[i]
    }
    const ma = sa / n
    const mb = sb / n
    let num = 0, da = 0, db = 0
    for (let i = 0; i < n; i++) {
      const x = a[i] - ma
      const y = b[i] - mb
      num += x * y
      da += x * x
      db += y * y
    }
    const denom = Math.sqrt(da * db)
    if (denom === 0) return 0
    return num / denom
  }
  const out: Record<string, Record<string, number>> = {}
  for (const a of symbols) {
    out[a] = {}
    for (const b of symbols) {
      out[a][b] = a === b ? 1 : pearson(returns[a], returns[b])
    }
  }
  return out
}

/**
 * "Defensive crowding" — operator's native breadth-divergence cue.
 *
 * Returns true when 2+ of the defensive sectors (per `SECTOR_ETFS`'s
 * `defensive: true` flag — XLP / XLU / XLV) occupy a top-3 RS rank.
 * The Sectors page background gets a subtle stress-tinted wash when
 * this fires.
 */
export function defensiveCrowding(
  ranks: Record<string, number | null>,
  topN: number = 3,
  minDefensives: number = 2,
): boolean {
  const defensives = SECTOR_ETFS.filter((s) => s.defensive).map((s) => s.symbol)
  let hits = 0
  for (const sym of defensives) {
    const r = ranks[sym]
    if (r != null && r <= topN) hits += 1
  }
  return hits >= minDefensives
}
