import { useNavigate, useParams } from 'react-router-dom'
import { DocViewer } from '../components/DocViewer'
import { DOCS, getDoc } from '../docs'

export function Docs() {
  const { slug } = useParams<{ slug?: string }>()
  const navigate = useNavigate()
  const doc = getDoc(slug)

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">
            Docs
          </h2>
          <p className="text-muted-foreground text-sm">
            Reference material for the platform — definitions, formulas, color legends.
          </p>
        </div>
        {/* Document switcher — segmented control */}
        <div
          role="tablist"
          aria-label="Document selector"
          className="inline-flex rounded-xl bg-background shadow-inset-sm p-1 gap-1"
        >
          {DOCS.map((d) => {
            const active = d.slug === doc.slug
            return (
              <button
                key={d.slug}
                role="tab"
                aria-selected={active}
                onClick={() => navigate(`/docs/${d.slug}`)}
                className={[
                  'px-3 py-1.5 rounded-lg text-xs transition-all',
                  active
                    ? 'bg-card text-foreground shadow-extruded-sm font-medium'
                    : 'text-muted-foreground hover:text-foreground',
                ].join(' ')}
              >
                {d.title}
              </button>
            )
          })}
        </div>
      </div>

      <DocViewer source={doc.source} />
    </div>
  )
}
