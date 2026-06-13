import { lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Today } from './pages/Today'
import { TickerLabels } from './pages/TickerLabels'
import { Motion } from './pages/Motion'
import { TickerHub } from './pages/TickerHub'
import { ThesesShell } from './pages/ThesesShell'
import { WatchlistConsolidated } from './pages/WatchlistConsolidated'
import { LazyRoute } from './components/common/LazyRoute'

// Lazy-load Docs so the markdown bundle (react-markdown + remark) only ships
// when the operator actually opens the page.
const Docs = lazy(() => import('./pages/Docs').then((m) => ({ default: m.Docs })))

// Lazy-load Macro so the Plotly bundle (chart-themes + plotly.js core +
// scatter/heatmap/candlestick/scatterpolar) ships only when the operator
// opens it. Same lazy-boundary strategy as before the lightweight-charts →
// Plotly swap; the Plotly bundle is bigger so this matters more, not less.
const Macro = lazy(() => import('./pages/Macro').then((m) => ({ default: m.Macro })))

// Lazy-load Predictions for the same Plotly-bundle-isolation reason as Macro.
// PredictionsByTarget pulls Plotly via CandlestickChart; keep it off the
// initial chunk so /today / /motion don't pay the cost.
const Predictions = lazy(() =>
  import('./pages/Predictions').then((m) => ({ default: m.Predictions })),
)

// Lazy-load Research (Phase 3.7).
const Research = lazy(() =>
  import('./pages/Research').then((m) => ({ default: m.Research })),
)

// Lazy-load TVContextInbox (Phase 2-6 TradingView context layer).
const TVContextInbox = lazy(() =>
  import('./pages/TVContextInbox').then((m) => ({ default: m.TVContextInbox })),
)

// Lazy-load TheStreet (Phase 2 IA reorg).
const TheStreet = lazy(() =>
  import('./pages/TheStreet').then((m) => ({ default: m.TheStreet })),
)

// Lazy-load Admin shell (Phase 3 cost-aware iteration). Routes:
//   /admin            → Admin (Processes default)
//   /admin/:tab       → Admin (cadences | costs | retention | schedule | jobs)
//   /admin/jobs/:jobId → Admin → JobsPanel renders AnalysisJobDetail
const Admin = lazy(() => import('./pages/Admin').then((m) => ({ default: m.Admin })))

// rx-finance pages (v1.x.1-a): now folded into Motion + Theses tab shells.
// RxFinance, RxFinanceDetail, RxFinancePositions are imported by
// pages/Motion.tsx; RxFinanceHypotheses by pages/ThesesShell.tsx. App-level
// routing only handles legacy `/rx-finance*` redirects below.

export function App() {
  return (
    <Layout>
      <Routes>
        {/* Today is the root. Legacy /admin/overview Dashboard removed 2026-05-17. */}
        <Route path="/" element={<Today />} />
        <Route path="/admin/overview" element={<Navigate to="/admin" replace />} />

        {/* Decide group — Macro / Predictions / Signals */}
        <Route
          path="/macro/:tab?"
          element={
            <LazyRoute Component={Macro} />
          }
        />
        <Route path="/predictions/:tab?" element={<LazyRoute Component={Predictions} />} />
        <Route path="/research" element={<LazyRoute Component={Research} />} />
        <Route path="/tv-context/:ticker?" element={<LazyRoute Component={TVContextInbox} />} />
        {/* Rec detail FIRST: more-specific route must register before the
            tab-only path so /motion/recs/:id binds the `id` param instead
            of being swallowed by the catch-all tab route. */}
        <Route path="/motion/recs/:id" element={<Motion />} />
        <Route path="/motion/:tab?" element={<Motion />} />

        {/* Think — The Street */}
        <Route path="/the-street" element={<LazyRoute Component={TheStreet} />} />

        {/* Ticker Hub — deep-linked from everywhere (no nav entry) */}
        <Route path="/ticker/:symbol" element={<TickerHub />} />

        {/* Phase 3 IA — Theses + consolidated Watchlist */}
        <Route path="/theses/:tab?" element={<ThesesShell />} />
        <Route path="/watchlist/:tab?" element={<WatchlistConsolidated />} />

        {/* Admin group — Phase 3 tabbed shell. Schedule + Jobs render inside. */}
        <Route path="/admin" element={<LazyRoute Component={Admin} />} />
        <Route path="/admin/:tab" element={<LazyRoute Component={Admin} />} />
        <Route path="/admin/:tab/:jobId" element={<LazyRoute Component={Admin} />} />
        <Route path="/tickers/:symbol/labels" element={<TickerLabels />} />

        {/* Legacy /rx-finance* paths redirect into Motion / Theses tabs. */}
        <Route path="/rx-finance" element={<Navigate to="/motion/recs" replace />} />
        <Route path="/rx-finance/hypotheses" element={<Navigate to="/theses/health" replace />} />
        <Route path="/rx-finance/positions" element={<Navigate to="/motion/positions" replace />} />
        <Route path="/rx-finance/:id" element={<LegacyRxDetailRedirect />} />

        {/* Phase 6 IA tweak: top-level /recs + /trades shortcuts for the
            highest-frequency daily workflows (UX strategist O8). Both
            redirect into the canonical Motion tab; preserves bookmarks
            but lets the operator type either URL. */}
        <Route path="/recs" element={<Navigate to="/motion/recs" replace />} />
        <Route path="/recs/:id" element={<LegacyRecsTopShortcut />} />
        <Route path="/trades" element={<Navigate to="/motion/trades" replace />} />

        {/* Legacy schedule + health redirect into the admin shell. */}
        <Route path="/schedule" element={<Navigate to="/admin/schedule" replace />} />
        <Route path="/health" element={<Navigate to="/admin/jobs" replace />} />
        <Route path="/health/:jobId" element={<LegacyHealthDetailRedirect />} />

        {/* Docs group */}
        <Route path="/docs/:slug?" element={<LazyRoute Component={Docs} />} />

        {/* Legacy redirects — old bookmarks + old tests still work */}
        <Route path="/predictions/by-horizon" element={<Navigate to="/predictions/horizon" replace />} />
        <Route path="/predictions/by-target"  element={<Navigate to="/predictions/target" replace />} />
        <Route path="/accuracy"               element={<Navigate to="/predictions/accuracy" replace />} />
        <Route path="/opportunities"          element={<Navigate to="/motion/opportunities" replace />} />
        {/* /trades shortcut already declared above (Phase 6 IA). Don't double-register. */}
        <Route path="/analysis"               element={<Navigate to="/health" replace />} />
        <Route path="/analysis/:jobId"        element={<LegacyAnalysisDetailRedirect />} />
        {/* Phase 3 IA: /watchlist is now the consolidated surface.
            Old /roster + /watchlists + /watchlists/:boardId redirect into it. */}
        <Route path="/roster"                 element={<Navigate to="/watchlist/roster" replace />} />
        <Route path="/watchlists"             element={<Navigate to="/watchlist" replace />} />
        <Route path="/watchlists/:boardId"    element={<Navigate to="/watchlist" replace />} />
      </Routes>
    </Layout>
  )
}

// Tiny helper: preserve the :jobId param when redirecting /analysis/:jobId → /admin/jobs/:jobId.
function LegacyAnalysisDetailRedirect() {
  const path = window.location.pathname.replace(/^\/analysis\//, '/admin/jobs/')
  return <Navigate to={path} replace />
}

// Preserve :jobId when redirecting /health/:jobId → /admin/jobs/:jobId.
function LegacyHealthDetailRedirect() {
  const path = window.location.pathname.replace(/^\/health\//, '/admin/jobs/')
  return <Navigate to={path} replace />
}

// Preserve :id when redirecting /rx-finance/:id → /motion/recs/:id.
function LegacyRxDetailRedirect() {
  const path = window.location.pathname.replace(/^\/rx-finance\//, '/motion/recs/')
  return <Navigate to={path} replace />
}

// Top-level /recs/:id shortcut → /motion/recs/:id (Phase 6 IA tweak).
function LegacyRecsTopShortcut() {
  const path = window.location.pathname.replace(/^\/recs\//, '/motion/recs/')
  return <Navigate to={path} replace />
}
