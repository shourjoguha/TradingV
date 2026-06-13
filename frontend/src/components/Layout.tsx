import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  Sun, AlertTriangle, BookOpen,
  LineChart as LineChartIcon, Brain, Zap, Sparkles, Camera, Building2,
  FlaskConical, Telescope,
} from 'lucide-react'
import { HypothesisStatusWidget } from './HypothesisStatusWidget'
import { RxStatusWidget } from './RxStatusWidget'
import { useHealth } from '../hooks/use-api'
import { useInboxTotal } from '../hooks/use-inbox-total'

function BackendHealthBanner() {
  const health = useHealth()
  if (!health.isError) return null
  return (
    <div className="bg-warning-bg text-warning-fg px-4 md:px-8 py-2 flex items-center gap-3 text-sm shadow-inset-sm">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <div className="flex-1">
        Cannot reach the backend. Health check failing — server may be stopped,
        or `localhost:8000` is unreachable.
      </div>
    </div>
  )
}

/**
 * Nav IA — icon rail + drawer-on-click. Clicking a rail icon either:
 *   - navigates directly (leaves: Today, Admin, Docs), or
 *   - opens a slide-out drawer with the section's children (Decide, Think).
 *
 * Re-imagination 2026-05-17:
 *   - Persistent 240px sidebar replaced w/ a 56px icon rail (always visible)
 *     + a 240px drawer that appears only when a section is clicked. Drawer
 *     auto-closes on navigation or Esc, frees the canvas the rest of the
 *     time. Operator stays one click from any route via the rail's tooltip
 *     icons.
 *   - Collapsibles removed entirely. Sections show flat lists w/ a section
 *     heading. No persisted collapse state, no auto-expand surprises.
 *   - Admin demoted to a leaf (single panel) after the legacy
 *     /admin/overview Dashboard was retired in the same pass.
 *   - Topbar shrunk; backend toggle removed (Railway shut down per
 *     ADR 018).
 *
 * Ticker Hub (`/ticker/:symbol`) is deep-linked from everywhere; not in nav.
 */
type NavLeaf = { kind: 'leaf'; id: string; path: string; label: string; icon: any }
type NavSection = { kind: 'section'; id: string; label: string; icon: any; children: NavChild[] }
type NavChild = { path: string; label: string; icon?: any }
type NavEntry = NavLeaf | NavSection

const NAV_ENTRIES: NavEntry[] = [
  { kind: 'leaf', id: 'today', path: '/', label: 'Today', icon: Sun },
  // Think before Decide (2026-05-17): operator IA preference — narrative /
  // intelligence surfaces (research, theses, vault, macro context) are the
  // first stop after the morning glance, *then* the numerical decision
  // surfaces. Macro relocated from Decide → Think because operator reads
  // macro as regime context (narrative input), not a daily decision lever.
  {
    kind: 'section',
    id: 'think',
    label: 'Think',
    icon: Brain,
    children: [
      { path: '/research', label: 'Research', icon: Sparkles },
      { path: '/theses', label: 'Theses', icon: FlaskConical },
      { path: '/macro', label: 'Macro', icon: Telescope },
      { path: '/tv-context', label: 'TV Context', icon: Camera },
      { path: '/the-street', label: 'The Street', icon: Building2 },
    ],
  },
  {
    kind: 'section',
    id: 'decide',
    label: 'Decide',
    icon: LineChartIcon,
    children: [
      { path: '/motion', label: 'Signals' },
      { path: '/predictions', label: 'Predictions' },
      { path: '/watchlist', label: 'Watchlist' },
    ],
  },
  { kind: 'leaf', id: 'admin', path: '/admin', label: 'Admin', icon: Zap },
  { kind: 'leaf', id: 'docs', path: '/docs', label: 'Docs', icon: BookOpen },
]

function pathMatches(pathname: string, target: string): boolean {
  if (target === '/') return pathname === '/'
  return pathname === target || pathname.startsWith(target + '/')
}

function isEntryActive(entry: NavEntry, pathname: string): boolean {
  if (entry.kind === 'leaf') return pathMatches(pathname, entry.path)
  return entry.children.some((c) => pathMatches(pathname, c.path))
}

/**
 * Resolve the section a pathname belongs to. Used by the topbar to switch
 * from breadcrumb-mode (for leaves like /, /admin, /docs) to tab-mode
 * (for /motion, /predictions, /macro, /watchlist → Decide;
 * /research, /theses, /tv-context, /the-street → Think).
 *
 * Returns null when the route is a leaf, deep-link (e.g. /ticker/:symbol),
 * or unmatched — caller falls back to breadcrumb.
 */
function findCurrentSection(pathname: string): NavSection | null {
  for (const entry of NAV_ENTRIES) {
    if (
      entry.kind === 'section' &&
      entry.children.some((c) => pathMatches(pathname, c.path))
    ) {
      return entry
    }
  }
  return null
}

function RailIcon({
  entry,
  active,
  onClick,
}: {
  entry: NavEntry
  active: boolean
  onClick: () => void
}) {
  const Icon = entry.icon
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={entry.label}
      title={entry.label}
      className={[
        'h-11 w-11 flex items-center justify-center rounded-2xl transition-all duration-150',
        active
          ? 'shadow-inset-sm text-primary'
          : 'text-muted-foreground hover:text-foreground hover:shadow-extruded-sm',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background',
      ].join(' ')}
    >
      <Icon className="h-5 w-5" />
    </button>
  )
}

function DrawerPanel({
  section,
  pathname,
  onNavigate,
}: {
  section: NavSection
  pathname: string
  onNavigate: () => void
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-6 pt-6 pb-3">
        <div className="text-xs font-mono text-muted-foreground">
          {section.label}
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 space-y-1">
        {section.children.map((child) => {
          const active = pathMatches(pathname, child.path)
          const ChildIcon = child.icon
          return (
            <Link
              key={child.path}
              to={child.path}
              onClick={onNavigate}
              className={[
                'flex items-center gap-3 px-4 py-3 rounded-2xl text-sm font-medium transition-all duration-200 min-h-[44px]',
                active
                  ? 'shadow-inset-sm text-primary bg-background'
                  : 'text-muted-foreground hover:text-foreground hover:shadow-extruded-sm',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background',
              ].join(' ')}
            >
              {ChildIcon && <ChildIcon className="h-4 w-4" />}
              <span>{child.label}</span>
            </Link>
          )
        })}
      </nav>
      <div className="pt-2">
        <RxStatusWidget />
        <HypothesisStatusWidget />
      </div>
    </div>
  )
}

/**
 * KLogoLink — home link + ambient attention ring.
 *
 * Phase 6 color taxonomy (motion designer council): the K-glyph in the
 * rail breathes a primary box-shadow ring (0.10 → 0.22 alpha at 3.2s
 * ease-in-out infinite) when total inbox count > 0. Peripheral-vision
 * channel — operator never has to look at it directly, but they "feel
 * the room go quiet" when inbox hits zero. One signal app-wide;
 * deliberately constrained per the no-decoration rule.
 */
function KLogoLink({ onClick }: { onClick: () => void }) {
  const inboxTotal = useInboxTotal()
  const ringClass = inboxTotal > 0 ? 'animate-attention-pulse' : ''
  return (
    <Link
      to="/"
      aria-label="Kronos home"
      title={inboxTotal > 0 ? `Kronos · Today (${inboxTotal} in inbox)` : 'Kronos · Today'}
      onClick={onClick}
      className={`h-10 w-10 flex items-center justify-center rounded-2xl font-display font-extrabold text-base text-primary shadow-extruded-sm hover:shadow-extruded transition-all mb-2 ${ringClass}`}
    >
      K
    </Link>
  )
}

function TopbarSectionTabs({
  section,
  pathname,
}: {
  section: NavSection
  pathname: string
}) {
  const SectionIcon = section.icon
  return (
    <div className="flex items-center gap-3 min-w-0 w-full">
      <div className="flex items-center gap-2 shrink-0">
        <SectionIcon className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold text-foreground">
          {section.label}
        </span>
      </div>
      <div className="h-4 w-px bg-border/60 shrink-0" aria-hidden />
      <nav
        className="flex items-center gap-1 overflow-x-auto"
        aria-label={`${section.label} tabs`}
      >
        {section.children.map((child) => {
          const active = pathMatches(pathname, child.path)
          return (
            <Link
              key={child.path}
              to={child.path}
              className={[
                'px-3 py-1.5 rounded-xl text-sm font-medium transition-all duration-150 whitespace-nowrap',
                active
                  ? 'shadow-inset-sm text-primary'
                  : 'text-muted-foreground hover:text-foreground hover:shadow-extruded-sm',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background',
              ].join(' ')}
            >
              {child.label}
            </Link>
          )
        })}
      </nav>
    </div>
  )
}

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [openSection, setOpenSection] = useState<string | null>(null)

  // Drawer auto-closes on navigation — keeps the canvas clear once you've
  // picked a destination. Operator can re-open via the rail any time.
  useEffect(() => {
    setOpenSection(null)
  }, [location.pathname])

  // Esc collapses the drawer (a11y muscle memory).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpenSection(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Lock body scroll while the overlay is up (matters on mobile).
  useEffect(() => {
    document.body.style.overflow = openSection ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [openSection])

  const breadcrumb =
    location.pathname === '/'
      ? 'Today'
      : location.pathname.split('/').filter(Boolean).join(' / ')

  const openEntry =
    openSection
      ? (NAV_ENTRIES.find(
          (e) => e.id === openSection && e.kind === 'section',
        ) as NavSection | undefined)
      : undefined

  // Topbar adapts: section-aware tabs for /motion, /predictions, ...
  // (Decide/Think children); breadcrumb-only for leaves + deep-links.
  const sectionForTopbar = findCurrentSection(location.pathname)

  function handleRailClick(entry: NavEntry) {
    if (entry.kind === 'leaf') {
      navigate(entry.path)
      setOpenSection(null)
      return
    }
    setOpenSection((cur) => (cur === entry.id ? null : entry.id))
  }

  return (
    <div className="min-h-screen w-full bg-background text-foreground">
      {/* Icon rail — 56px, fixed, always visible (incl. mobile). */}
      <aside className="fixed left-0 top-0 bottom-0 w-14 flex flex-col items-center py-3 bg-background shadow-extruded z-50">
        <KLogoLink onClick={() => setOpenSection(null)} />
        <nav className="flex-1 flex flex-col items-center gap-1 mt-2">
          {NAV_ENTRIES.map((entry) => (
            <RailIcon
              key={entry.id}
              entry={entry}
              active={
                isEntryActive(entry, location.pathname) || openSection === entry.id
              }
              onClick={() => handleRailClick(entry)}
            />
          ))}
        </nav>
      </aside>

      {/* Drawer + backdrop (only when a section is open). */}
      {openEntry && (
        <>
          <div
            className="fixed inset-0 z-30 bg-black/20 backdrop-blur-[1px]"
            onClick={() => setOpenSection(null)}
            aria-hidden
          />
          <aside
            className="fixed left-14 top-0 bottom-0 w-60 flex flex-col bg-background shadow-extruded z-40 animate-in slide-in-from-left duration-150"
            role="dialog"
            aria-label={`${openEntry.label} menu`}
          >
            <DrawerPanel
              section={openEntry}
              pathname={location.pathname}
              onNavigate={() => setOpenSection(null)}
            />
          </aside>
        </>
      )}

      {/* Main column — always offset by the rail (56px). */}
      <main className="ml-14 flex flex-col min-h-screen">
        {/* Translucent topbar — float over content w/ a thin underline so
            the body reads as a separate plane underneath. Section-aware:
            tabs for Decide/Think, breadcrumb for leaves + deep-links. */}
        <header className="sticky top-0 h-14 bg-background/30 backdrop-blur-xl flex items-center px-4 md:px-6 z-20 border-b border-border/30 shadow-[0_1px_6px_rgba(163,177,198,0.06)]">
          {sectionForTopbar ? (
            <TopbarSectionTabs
              section={sectionForTopbar}
              pathname={location.pathname}
            />
          ) : (
            <div className="font-medium text-sm text-muted-foreground capitalize truncate">
              {breadcrumb}
            </div>
          )}
        </header>

        <BackendHealthBanner />

        <div className="flex-1 p-4 md:p-8">
          <div className="max-w-7xl mx-auto">{children}</div>
        </div>
      </main>
    </div>
  )
}
