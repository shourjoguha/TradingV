import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Watchlist } from './pages/Watchlist'
import { Schedule } from './pages/Schedule'
import { TickerLabels } from './pages/TickerLabels'
import { AnalysisJobs } from './pages/AnalysisJobs'
import { AnalysisJobDetail } from './pages/AnalysisJobDetail'
import { PredictionsByTarget } from './pages/PredictionsByTarget'
import { PredictionsByHorizon } from './pages/PredictionsByHorizon'
import { Accuracy } from './pages/Accuracy'
import { Opportunities } from './pages/Opportunities'
import { Trades } from './pages/Trades'
import { Skeleton } from './components/ui/skeleton'

// Lazy-load Docs so the markdown bundle (react-markdown + remark) only ships
// when the operator actually opens the page.
const Docs = lazy(() => import('./pages/Docs').then((m) => ({ default: m.Docs })))

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/watchlist" element={<Watchlist />} />
        <Route path="/schedule" element={<Schedule />} />
        <Route path="/predictions/by-target" element={<PredictionsByTarget />} />
        <Route path="/predictions/by-horizon" element={<PredictionsByHorizon />} />
        <Route path="/tickers/:symbol/labels" element={<TickerLabels />} />
        <Route path="/analysis" element={<AnalysisJobs />} />
        <Route path="/analysis/:jobId" element={<AnalysisJobDetail />} />
        <Route path="/accuracy" element={<Accuracy />} />
        <Route path="/opportunities" element={<Opportunities />} />
        <Route path="/trades" element={<Trades />} />
        <Route
          path="/docs/:slug?"
          element={
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <Docs />
            </Suspense>
          }
        />
      </Routes>
    </Layout>
  )
}
