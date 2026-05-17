/**
 * TabbedShell — canonical neumorphic page-tab pattern.
 *
 * Replaces 7 hand-rolled implementations:
 *   - Motion.tsx, Predictions.tsx, Macro.tsx, Admin.tsx,
 *     TheStreet.tsx, ThesesShell.tsx, WatchlistConsolidated.tsx
 *
 * Pattern (per .claude/frontend/ui-components.md §A — Page tabs):
 *   - inset shell, extruded thumb
 *   - default tab = first tab in list (or explicit prop)
 *   - URL pattern: `/<basePath>` (default) and `/<basePath>/<tabId>`
 *   - ARIA: role tablist + tab + selected
 *
 * Detail short-circuit: pass `detailMatch` to render a custom node when
 * the URL pattern indicates a detail page (e.g. `/motion/recs/:id`).
 */
import { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

export interface TabDef {
  id: string
  label: string
  render: () => ReactNode
}

export interface TabbedShellProps {
  /** URL prefix without trailing slash, e.g. "/motion". */
  basePath: string
  /** Tab definitions, first one is the default when URL has no :tab. */
  tabs: TabDef[]
  /** When true, render `detail` instead of the tab shell. */
  isDetail?: boolean
  /** Detail-page renderer (used when `isDetail` is true). */
  detail?: ReactNode
  /** ARIA label. */
  ariaLabel?: string
}

export function TabbedShell({
  basePath,
  tabs,
  isDetail = false,
  detail,
  ariaLabel,
}: TabbedShellProps) {
  const { tab: tabParam } = useParams<{ tab?: string }>()
  const navigate = useNavigate()

  if (isDetail && detail) return <>{detail}</>

  const defaultId = tabs[0]?.id ?? ''
  const active = tabs.find((t) => t.id === tabParam)?.id ?? defaultId
  const activeDef = tabs.find((t) => t.id === active)

  return (
    <div className="space-y-4">
      <div
        role="tablist"
        aria-label={ariaLabel ?? `${basePath} view`}
        className="inline-flex rounded-xl bg-background shadow-inset-sm p-1 gap-1"
      >
        {tabs.map((t) => {
          const isActive = t.id === active
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={isActive}
              onClick={() =>
                navigate(t.id === defaultId ? basePath : `${basePath}/${t.id}`)
              }
              className={[
                'px-3 py-1.5 rounded-lg text-xs transition-all',
                isActive
                  ? 'bg-card text-foreground shadow-extruded-sm font-medium'
                  : 'text-muted-foreground hover:text-foreground',
              ].join(' ')}
            >
              {t.label}
            </button>
          )
        })}
      </div>
      {activeDef?.render()}
    </div>
  )
}
