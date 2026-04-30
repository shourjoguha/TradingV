import { useNavigate, useParams } from 'react-router-dom'
import { PredictionsByHorizon } from './PredictionsByHorizon'
import { PredictionsByTarget } from './PredictionsByTarget'
import { Accuracy } from './Accuracy'

type Tab = 'horizon' | 'target' | 'accuracy'
const TABS: { id: Tab; label: string }[] = [
  { id: 'horizon',  label: 'By Horizon' },
  { id: 'target',   label: 'By Target' },
  { id: 'accuracy', label: 'Accuracy' },
]

// Wrapper with the same segmented-tab pattern as /macro. Existing inner
// pages render unchanged — they own their own headers/controls — so
// migration to the grouped sidebar IA is purely additive.
export function Predictions() {
  const { tab: tabParam } = useParams<{ tab?: string }>()
  const navigate = useNavigate()
  const tab: Tab = (TABS.find((t) => t.id === tabParam)?.id ?? 'horizon') as Tab

  return (
    <div className="space-y-4">
      <div
        role="tablist"
        aria-label="Predictions view"
        className="inline-flex rounded-xl bg-background shadow-inset-sm p-1 gap-1"
      >
        {TABS.map((t) => {
          const active = t.id === tab
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={active}
              onClick={() =>
                navigate(t.id === 'horizon' ? '/predictions' : `/predictions/${t.id}`)
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

      {tab === 'horizon' && <PredictionsByHorizon />}
      {tab === 'target' && <PredictionsByTarget />}
      {tab === 'accuracy' && <Accuracy />}
    </div>
  )
}

export default Predictions
