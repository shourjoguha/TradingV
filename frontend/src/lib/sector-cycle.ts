/**
 * Business-cycle phase classifier + sector→phase canonical mapping.
 *
 * The Cycle Phase Wheel (Macro › Sectors sub-tab) needs two things:
 *   1. A *current phase* (Early / Mid / Late / Recession) inferred from
 *      a defensible macro indicator.
 *   2. A *canonical favored sector* mapping per phase, used to position
 *      each sector dot in its primary quadrant on the wheel.
 *
 * **Phase detection** — uses the 10y-2y Treasury spread (`T10Y2Y` series,
 * already cached as part of the Yield curve regime panel) plus the
 * 12-month change in that spread:
 *
 *   spread > +1.0 AND steepening (Δ12m > 0)     → Early    (recovery underway)
 *   spread > 0   AND flattening (Δ12m < 0)      → Mid      (expansion sustained)
 *   spread ≤ 0                                  → Late     (curve inverted)
 *   spread > 0 AND was ≤ 0 within last 12m      → Recession transition (re-steepening from inversion)
 *
 * Falls back to `'mid'` when insufficient history. Single-indicator classifier
 * is intentionally simple — operator can sanity-check by eye. Future tuning
 * could blend ISM PMI or unemployment, but Out Of Scope per the council pick
 * (one indicator, one defensible read).
 *
 * **Sector mapping** — Fidelity / SSGA business-cycle approach. Each sector
 * is tagged with its single *most* favored phase; a sector may perform well
 * in more than one (e.g. Tech in both Early and Mid), but the wheel needs
 * a primary placement, so we pick the strongest-statistical phase per the
 * Fidelity Leadership Series PDF (cited in plan-file Sources section).
 */
import type { MacroPoint } from './types'

export type CyclePhase = 'early' | 'mid' | 'late' | 'recession'

export interface PhaseMeta {
  id: CyclePhase
  /** Short label for the wheel arc */
  label: string
  /** One-line tooltip explainer */
  blurb: string
  /** Wheel position: angle in degrees from 12 o'clock, clockwise */
  startAngle: number
  endAngle: number
}

export const PHASES: Record<CyclePhase, PhaseMeta> = {
  early: {
    id: 'early',
    label: 'Early',
    blurb:
      'Recovery underway. Curve steep + steepening. Cyclicals lead — Discretionary, Financials, Industrials, Tech.',
    startAngle: 270,
    endAngle: 360,
  },
  mid: {
    id: 'mid',
    label: 'Mid',
    blurb:
      'Sustained expansion. Curve still positive but flattening. Tech + Industrials persist; rotation slows.',
    startAngle: 0,
    endAngle: 90,
  },
  late: {
    id: 'late',
    label: 'Late',
    blurb:
      'Growth peaking. Curve inverts. Commodities + early-defensives bid: Energy, Materials, Staples, Health.',
    startAngle: 90,
    endAngle: 180,
  },
  recession: {
    id: 'recession',
    label: 'Recession',
    blurb:
      'Contraction. Curve re-steepening from inversion. Pure defensives: Staples, Health, Utilities.',
    startAngle: 180,
    endAngle: 270,
  },
}

/** Per-sector canonical primary-favored phase (Fidelity / SSGA taxonomy). */
export const SECTOR_PHASE: Record<string, CyclePhase> = {
  XLY: 'early',  // Discretionary — early-cycle consumer
  XLF: 'early',  // Financials — yield-curve steepening tailwind
  XLI: 'mid',    // Industrials — capex / production cycle
  XLK: 'mid',    // Tech — mid-cycle capex on productivity
  XLE: 'late',   // Energy — late-cycle commodity demand
  XLB: 'late',   // Materials — late-cycle commodity demand
  XLV: 'recession', // Health — defensive demand floor
  XLP: 'recession', // Staples — defensive demand floor
  XLU: 'recession', // Utilities — defensive yield + low beta
}

/**
 * Classify the current cycle phase from a `T10Y2Y` series (10y-2y spread).
 * Series is daily Close from FRED; the spread is already expressed in
 * percentage points (e.g. 0.50 = 50 bps).
 */
export function detectCyclePhase(t10y2y: MacroPoint[]): {
  phase: CyclePhase
  spread: number | null
  trend: 'steepening' | 'flattening' | 'flat' | null
} {
  if (t10y2y.length === 0) {
    return { phase: 'mid', spread: null, trend: null }
  }
  const last = t10y2y[t10y2y.length - 1].value
  // 12-month lookback (≈ 252 trading days)
  const window = Math.min(252, t10y2y.length - 1)
  const past = t10y2y[t10y2y.length - 1 - window].value
  const delta = last - past
  const trend: 'steepening' | 'flattening' | 'flat' =
    Math.abs(delta) < 0.1 ? 'flat' : delta > 0 ? 'steepening' : 'flattening'

  // Was the curve inverted at any point in the last 12 months?
  let wasInverted = false
  for (let i = t10y2y.length - 1 - window; i < t10y2y.length; i++) {
    if (t10y2y[i].value <= 0) {
      wasInverted = true
      break
    }
  }

  let phase: CyclePhase
  if (last <= 0) {
    phase = 'late'
  } else if (wasInverted && trend === 'steepening') {
    phase = 'recession'
  } else if (last > 1.0 && trend === 'steepening') {
    phase = 'early'
  } else {
    phase = 'mid'
  }

  return { phase, spread: last, trend }
}
