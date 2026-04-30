import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Watchlist } from './pages/Watchlist'
import { Schedule } from './pages/Schedule'
import { TickerLabels } from './pages/TickerLabels'
import { AnalysisJobs } from './pages/AnalysisJobs'
import { AnalysisJobDetail } from './pages/AnalysisJobDetail'
import { Predictions } from './pages/Predictions'
import { Motion } from './pages/Motion'
import { Skeleton } from './components/ui/skeleton'

// Lazy-load Docs so the markdown bundle (react-markdown + remark) only ships
// when the operator actually opens the page.
const Docs = lazy(() => import('./pages/Docs').then((m) => ({ default: m.Docs })))

// Lazy-load Macro so lightweight-charts ships only when the operator opens it.
const Macro = lazy(() => import('./pages/Macro').then((m) => ({ default: m.Macro })))

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />

        {/* Decisions group — Macro / Predictions / Motion */}
        <Route
          path="/macro/:tab?"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <Macro />
            </Suspense>
          }
        />
        <Route path="/predictions/:tab?" element={<Predictions />} />
        <Route path="/motion/:tab?" element={<Motion />} />

        {/* Admin group — Roster / Schedule / Health */}
        <Route path="/roster" element={<Watchlist />} />
        <Route path="/schedule" element={<Schedule />} />
        <Route path="/health" element={<AnalysisJobs />} />
        <Route path="/health/:jobId" element={<AnalysisJobDetail />} />
        <Route path="/tickers/:symbol/labels" element={<TickerLabels />} />

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
        <Route path="/watchlist"              element={<Navigate to="/roster" replace />} />
      </Routes>
    </Layout>
  )
}

// Tiny helper: preserve the :jobId param when redirecting /analysis/:jobId → /health/:jobId.
function LegacyAnalysisDetailRedirect() {
  const path = window.location.pathname.replace(/^\/analysis\//, '/health/')
  return <Navigate to={path} replace />
}
