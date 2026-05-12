import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Today } from './pages/Today'
import { Dashboard } from './pages/Dashboard'
import { TickerLabels } from './pages/TickerLabels'
import { Predictions } from './pages/Predictions'
import { Motion } from './pages/Motion'
import { TickerHub } from './pages/TickerHub'
import { Theses } from './pages/Theses'
import { WatchlistConsolidated } from './pages/WatchlistConsolidated'
import { Skeleton } from './components/ui/skeleton'

// Lazy-load Docs so the markdown bundle (react-markdown + remark) only ships
// when the operator actually opens the page.
const Docs = lazy(() => import('./pages/Docs').then((m) => ({ default: m.Docs })))

// Lazy-load Macro so lightweight-charts ships only when the operator opens it.
const Macro = lazy(() => import('./pages/Macro').then((m) => ({ default: m.Macro })))

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

export function App() {
  return (
    <Layout>
      <Routes>
        {/* Phase 1 IA: Today is the new root; legacy Dashboard moves to /admin/overview. */}
        <Route path="/" element={<Today />} />
        <Route path="/admin/overview" element={<Dashboard />} />

        {/* Decide group — Macro / Predictions / Signals */}
        <Route
          path="/macro/:tab?"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <Macro />
            </Suspense>
          }
        />
        <Route path="/predictions/:tab?" element={<Predictions />} />
        <Route
          path="/research"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <Research />
            </Suspense>
          }
        />
        <Route
          path="/tv-context/:ticker?"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <TVContextInbox />
            </Suspense>
          }
        />
        <Route path="/motion/:tab?" element={<Motion />} />

        {/* Think — The Street */}
        <Route
          path="/the-street"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <TheStreet />
            </Suspense>
          }
        />

        {/* Ticker Hub — deep-linked from everywhere (no nav entry) */}
        <Route path="/ticker/:symbol" element={<TickerHub />} />

        {/* Phase 3 IA — Theses + consolidated Watchlist */}
        <Route path="/theses" element={<Theses />} />
        <Route path="/watchlist/:tab?" element={<WatchlistConsolidated />} />

        {/* Admin group — Phase 3 tabbed shell. Schedule + Jobs render inside. */}
        <Route
          path="/admin"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <Admin />
            </Suspense>
          }
        />
        <Route
          path="/admin/:tab"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <Admin />
            </Suspense>
          }
        />
        <Route
          path="/admin/:tab/:jobId"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <Admin />
            </Suspense>
          }
        />
        <Route path="/tickers/:symbol/labels" element={<TickerLabels />} />

        {/* Legacy schedule + health redirect into the admin shell. */}
        <Route path="/schedule" element={<Navigate to="/admin/schedule" replace />} />
        <Route path="/health" element={<Navigate to="/admin/jobs" replace />} />
        <Route path="/health/:jobId" element={<LegacyHealthDetailRedirect />} />

        {/* Docs group */}
        <Route
          path="/docs/:slug?"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <Docs />
            </Suspense>
          }
        />

        {/* Legacy redirects — old bookmarks + old tests still work */}
        <Route path="/predictions/by-horizon" element={<Navigate to="/predictions/horizon" replace />} />
        <Route path="/predictions/by-target"  element={<Navigate to="/predictions/target" replace />} />
        <Route path="/accuracy"               element={<Navigate to="/predictions/accuracy" replace />} />
        <Route path="/opportunities"          element={<Navigate to="/motion/opportunities" replace />} />
        <Route path="/trades"                 element={<Navigate to="/motion/trades" replace />} />
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
