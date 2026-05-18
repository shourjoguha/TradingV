import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSlug from 'rehype-slug'

interface Heading {
  id: string
  text: string
  level: number
}

// GitHub-style slugifier compatible with rehype-slug's default. Lowercase,
// strip non-word/space, collapse spaces to dashes. Keeps anchor refs stable
// across re-renders without needing to pull rehype-slug's util.
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
}

// Extract h2/h3 headings from raw markdown for the TOC. We avoid h1 because
// each doc has exactly one title and the page header already shows it.
function extractHeadings(source: string): Heading[] {
  const out: Heading[] = []
  const lines = source.split('\n')
  let inFence = false
  for (const line of lines) {
    if (/^```/.test(line)) {
      inFence = !inFence
      continue
    }
    if (inFence) continue
    const m = /^(#{2,3})\s+(.+?)\s*$/.exec(line)
    if (!m) continue
    const level = m[1].length
    const text = m[2].replace(/`/g, '')
    out.push({ id: slugify(text), text, level })
  }
  return out
}

// Scroll-spy: track which heading is "active" by picking the topmost one
// currently intersecting the viewport. Falls back to the last passed
// heading if nothing intersects (e.g. user scrolled past everything).
function useActiveHeading(ids: string[], rootRef: React.RefObject<HTMLElement>) {
  const [active, setActive] = useState<string | null>(ids[0] ?? null)
  useEffect(() => {
    if (ids.length === 0) return
    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null)
    if (elements.length === 0) return

    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible.length > 0) {
          setActive(visible[0].target.id)
          return
        }
      },
      { rootMargin: '-80px 0px -60% 0px', threshold: [0, 1] },
    )

    elements.forEach((el) => obs.observe(el))
    return () => obs.disconnect()
  }, [ids.join('|'), rootRef])

  return active
}

const FONT_KEY = 'docs.fontSize'
type FontSize = 'sm' | 'md' | 'lg'
const FONT_PX: Record<FontSize, string> = { sm: '14px', md: '16px', lg: '18px' }

interface DocViewerProps {
  source: string
}

export function DocViewer({ source }: DocViewerProps) {
  const articleRef = useRef<HTMLElement>(null)
  const headings = useMemo(() => extractHeadings(source), [source])
  const ids = useMemo(() => headings.map((h) => h.id), [headings])
  const active = useActiveHeading(ids, articleRef as any)

  const [fontSize, setFontSize] = useState<FontSize>(() => {
    if (typeof window === 'undefined') return 'md'
    const stored = window.localStorage.getItem(FONT_KEY)
    return stored === 'sm' || stored === 'md' || stored === 'lg' ? stored : 'md'
  })
  useEffect(() => {
    window.localStorage.setItem(FONT_KEY, fontSize)
  }, [fontSize])

  const onTocClick = (id: string) => (e: React.MouseEvent) => {
    e.preventDefault()
    const el = document.getElementById(id)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    history.replaceState(null, '', `#${id}`)
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-6">
      {/* TOC — sticky on lg+, accordion on mobile. Light visual separator
          from article: subtle right-border + `pr-4` inner padding so the
          TOC reads as a distinct rail rather than free-floating text. */}
      <aside className="lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:border-r lg:border-border/40 lg:pr-4">
        <details className="lg:open" open>
          <summary className="lg:hidden cursor-pointer text-xs font-semibold text-muted-foreground py-2">
            On this page
          </summary>
          <div className="hidden lg:block text-[11px] font-semibold text-muted-foreground mb-2 px-2">
            On this page
          </div>
          <ul className="space-y-0.5 text-sm">
            {headings.map((h) => {
              const isActive = active === h.id
              return (
                <li key={h.id} className={h.level === 3 ? 'ml-3' : ''}>
                  <a
                    href={`#${h.id}`}
                    onClick={onTocClick(h.id)}
                    className={[
                      'block px-2 py-1 rounded-md transition-colors',
                      isActive
                        ? 'bg-accent text-accent-foreground font-medium'
                        : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
                    ].join(' ')}
                  >
                    {h.text}
                  </a>
                </li>
              )
            })}
          </ul>
        </details>
      </aside>

      {/* Article */}
      <div className="min-w-0">
        {/* Font-size adjuster */}
        <div className="flex items-center justify-end gap-1 mb-3">
          <span className="text-[11px] text-muted-foreground mr-1">Text size</span>
          {(['sm', 'md', 'lg'] as FontSize[]).map((s) => (
            <button
              key={s}
              onClick={() => setFontSize(s)}
              className={[
                'px-2 py-1 rounded-md text-xs font-mono transition-colors',
                fontSize === s
                  ? 'bg-accent text-accent-foreground shadow-extruded-sm'
                  : 'text-muted-foreground hover:bg-muted/50',
              ].join(' ')}
              aria-pressed={fontSize === s}
              aria-label={`Set text size ${s}`}
            >
              {s === 'sm' ? 'A−' : s === 'md' ? 'A' : 'A+'}
            </button>
          ))}
        </div>

        <article
          ref={articleRef}
          className="docs-article max-w-3xl"
          style={{ fontSize: FONT_PX[fontSize] }}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSlug]}
          >
            {source}
          </ReactMarkdown>
        </article>
      </div>
    </div>
  )
}
