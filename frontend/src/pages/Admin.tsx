import { useNavigate, useParams } from 'react-router-dom'
import { ProcessesTab } from '../components/admin/ProcessesTab'
import { CadencesTab } from '../components/admin/CadencesTab'
import { CostsTab } from '../components/admin/CostsTab'
import { RetentionTab } from '../components/admin/RetentionTab'
import { SchedulePanel } from '../components/admin/SchedulePanel'
import { JobsPanel } from '../components/admin/JobsPanel'
import { TabErrorBoundary } from '../components/admin/ErrorBoundary'

type Tab =
  | 'processes'
  | 'cadences'
  | 'costs'
  | 'retention'
  | 'schedule'
  | 'jobs'

const TABS: { id: Tab; label: string }[] = [
  { id: 'processes', label: 'Processes' },
  { id: 'cadences', label: 'Cadences' },
  { id: 'costs', label: 'Costs' },
  { id: 'retention', label: 'Retention' },
  { id: 'schedule', label: 'Schedule' },
  { id: 'jobs', label: 'Jobs' },
]

// Tab shell mirroring /predictions and /macro. Each tab is conditionally
// rendered (lazy mount) so a tab with no fetches stays cheap, and the
// `<TabErrorBoundary>` keeps a single broken tab from blanking the page.
export function Admin() {
  const { tab: tabParam } = useParams<{ tab?: string }>()
  const navigate = useNavigate()
  const tab: Tab = (TABS.find((t) => t.id === tabParam)?.id ?? 'processes') as Tab

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-heading font-semibold tracking-tight">Admin</h2>
      </div>

      <div
        role="tablist"
        aria-label="Admin sections"
        className="inline-flex rounded-xl bg-background shadow-inset-sm p-1 gap-1 flex-wrap"
      >
        {TABS.map((t) => {
          const active = t.id === tab
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={active}
              onClick={() =>
                navigate(t.id === 'processes' ? '/admin' : `/admin/${t.id}`)
              }
              className={[
                'px-3 py-1.5 rounded-lg text-xs transition-all',
                active
                  ? 'bg-card text-foreground shadow-extruded-sm font-medium'
                  : 'text-muted-foreground hover:text-foreground',
              ].join(' ')}
            >
              {t.label}
            </button>
          )
        })}
      </div>

      {tab === 'processes' && (
        <TabErrorBoundary label="processes">
          <ProcessesTab />
        </TabErrorBoundary>
      )}
      {tab === 'cadences' && (
        <TabErrorBoundary label="cadences">
          <CadencesTab />
        </TabErrorBoundary>
      )}
      {tab === 'costs' && (
        <TabErrorBoundary label="costs">
          <CostsTab />
        </TabErrorBoundary>
      )}
      {tab === 'retention' && (
        <TabErrorBoundary label="retention">
          <RetentionTab />
        </TabErrorBoundary>
      )}
      {tab === 'schedule' && (
        <TabErrorBoundary label="schedule">
          <SchedulePanel />
        </TabErrorBoundary>
      )}
      {tab === 'jobs' && (
        <TabErrorBoundary label="jobs">
          <JobsPanel />
        </TabErrorBoundary>
      )}
    </div>
  )
}

export default Admin
