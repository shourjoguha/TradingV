import { useEffect, useMemo } from 'react'
import { Badge } from '../ui/badge'
import { useResearchSkills } from '../../hooks/use-api'
import type { ResearchSkillInfo } from '../../lib/types'

const STORAGE_KEY = 'research.last_skill_slug'
const MOBILE_THRESHOLD = 4

interface Props {
  selected: string | null
  onChange: (slug: string | null) => void
}

function flattenDescription(s: string): string {
  return s.replace(/\s*\n\s*/g, ' ').trim()
}

function firstSentence(s: string): string {
  const flat = flattenDescription(s)
  const m = flat.match(/^(.{0,200}?[.!?])(\s|$)/)
  return m ? m[1] : flat.slice(0, 200)
}

export function SkillPicker({ selected, onChange }: Props) {
  const { data, isLoading } = useResearchSkills()
  const items: ResearchSkillInfo[] = useMemo(() => data?.items ?? [], [data])

  // Restore from localStorage on first render once skills are loaded.
  useEffect(() => {
    if (selected || items.length === 0) return
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored && items.some((s) => s.slug === stored)) {
      onChange(stored)
      return
    }
    const def = items.find((s) => s.default) ?? items[0]
    if (def) onChange(def.slug)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items])

  // Persist on change.
  useEffect(() => {
    if (selected) window.localStorage.setItem(STORAGE_KEY, selected)
  }, [selected])

  if (isLoading) {
    return (
      <div className="text-xs text-muted-foreground" data-testid="skill-picker-loading">
        Loading skills…
      </div>
    )
  }

  // Empty list fallback — hide picker entirely.
  if (items.length === 0) return null

  const active = items.find((s) => s.slug === selected) ?? null
  const useNativeSelect = items.length > MOBILE_THRESHOLD

  return (
    <div className="space-y-2" data-testid="skill-picker">
      <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
        Skill
      </div>

      {/* Desktop: filter-chip pattern matching HistoryList + AskInput hypothesis
          scope. Mobile fallback to native select when there are many skills. */}
      <div className={useNativeSelect ? 'block sm:hidden' : 'hidden'}>
        <select
          className="w-full rounded-2xl shadow-inset-sm bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet"
          value={selected ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
        >
          {items.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.title}
            </option>
          ))}
        </select>
      </div>

      <div
        className={
          useNativeSelect
            ? 'hidden sm:flex flex-wrap gap-2'
            : 'flex flex-wrap gap-2'
        }
      >
        {items.map((s) => {
          const isActive = s.slug === selected
          return (
            <button
              key={s.slug}
              type="button"
              onClick={() => onChange(s.slug)}
              title={flattenDescription(s.description)}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet rounded-full"
            >
              <Badge
                variant={isActive ? 'default' : 'outline'}
                className="cursor-pointer select-none"
              >
                {s.title}
              </Badge>
            </button>
          )
        })}
      </div>

      {active && (
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">
            {firstSentence(active.description)}
          </div>
          {active.tool === null && (
            <div
              className="text-[11px] text-warning-fg"
              data-testid="skill-picker-verdict-only"
            >
              Verdict-only — won't propose hypothesis updates.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
