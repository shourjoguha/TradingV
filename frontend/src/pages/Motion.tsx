import { useNavigate, useParams } from 'react-router-dom'
import { Opportunities } from './Opportunities'
import { Trades } from './Trades'

type Tab = 'opportunities' | 'trades'
const TABS: { id: Tab; label: string }[] = [
  { id: 'opportunities', label: 'Opportunities' },
  { id: 'trades',        label: 'Trades' },
]

// "Motion" groups what-could-happen (opportunities) with what-did-happen
// (trades) — both are decision-action surfaces that share the
// per-rule/per-hypothesis P&L story. Same wrapper shape as Predictions.
export function Motion() {
  const { tab: tabParam } = useParams<{ tab?: string }>()
  const navigate = useNavigate()
  const tab: Tab = (TABS.find((t) => t.id === tabParam)?.id ?? 'opportunities') as Tab

  return (
    <div className="space-y-4">
      <div
        role="tablist"
        aria-label="Motion view"
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
                navigate(
                  t.id === 'opportunities' ? '/motion' : `/motion/${t.id}`,
                )
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

      {tab === 'opportunities' && <Opportunities />}
      {tab === 'trades' && <Trades />}
    </div>
  )
}

export default Motion
