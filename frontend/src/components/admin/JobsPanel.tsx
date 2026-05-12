import { useParams } from 'react-router-dom'
import { AnalysisJobs } from '../../pages/AnalysisJobs'
import { AnalysisJobDetail } from '../../pages/AnalysisJobDetail'

// Renders the existing AnalysisJobs page (or a single job detail when
// /admin/jobs/:jobId is active). Existing components own their content;
// this is just a router-aware wrapper for the tab shell.
export function JobsPanel() {
  const { jobId } = useParams<{ jobId?: string }>()
  if (jobId) return <AnalysisJobDetail />
  return <AnalysisJobs />
}
