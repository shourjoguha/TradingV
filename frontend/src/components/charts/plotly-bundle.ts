/**
 * Custom Plotly bundle — registers only the trace types we use.
 *
 * Why: `plotly.js` ships ~3.5MB minified. The dist subsets (`plotly.js-basic-dist`
 * ~280KB, `plotly.js-finance-dist` ~400KB) bundle fixed trace sets. We use a
 * custom build via `plotly.js/lib/core` + selective register calls so the bundle
 * is the union of {what the app uses} ∪ {core overhead}, targeting ~700KB
 * uncompressed (~250KB gzip).
 *
 * Registered trace types (kept minimal — each register adds 30-150KB):
 *   - scatter      (line + markers, used by LineChart + prediction overlays)
 *   - candlestick  (PredictionsByTarget OHLC)
 *   - heatmap      (CorrelationHeatmap — Phase 5)
 *   - scatterpolar (CyclePhaseWheel — Phase 5)
 *   - barpolar     (CyclePhaseWheel quadrant slices — Phase 5)
 *
 * Deferred (uncomment in lockstep w/ the callsites that need them):
 *   - bar          → if DriftBar-style numeric bars ever migrate
 */
import Plotly from 'plotly.js/lib/core'
import scatter from 'plotly.js/lib/scatter'
import candlestick from 'plotly.js/lib/candlestick'
import heatmap from 'plotly.js/lib/heatmap'
import scatterpolar from 'plotly.js/lib/scatterpolar'
import barpolar from 'plotly.js/lib/barpolar'

let registered = false

/** Idempotent register call — safe to invoke on every chart mount. */
export function ensurePlotlyRegistered(): typeof Plotly {
  if (!registered) {
    Plotly.register([scatter, candlestick, heatmap, scatterpolar, barpolar])
    registered = true
  }
  return Plotly
}

export default Plotly
