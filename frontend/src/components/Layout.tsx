import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, List, Clock, FlaskConical,
  Menu, X, AlertTriangle, BookOpen, ChevronDown, ChevronRight,
  LineChart as LineChartIcon, BarChart3, Zap,
} from 'lucide-react'
import { BackendToggle } from './BackendToggle'
import { useHealth } from '../hooks/use-api'
import { useBackend } from '../hooks/use-backend'
import { availableBackends } from '../lib/backend-store'

function BackendHealthBanner() {
  const { backendId, setBackend } = useBackend()
  const health = useHealth()
  if (!health.isError) return null
  const others = availableBackends().filter((id) => id !== backendId)
  const otherId = others[0]
  return (
    <div className="bg-warning-bg text-warning-fg px-4 md:px-8 py-2 flex items-center gap-3 text-sm shadow-inset-sm">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <div className="flex-1">
        Cannot reach <span className="font-mono font-medium">{backendId}</span> backend.
        {' '}Health check failing — laptop may be asleep, Tailscale down, or server stopped.
      </div>
      {otherId && (
        <button
          onClick={() => setBackend(otherId)}
          className="text-xs font-medium px-3 py-1 rounded-xl shadow-extruded-sm hover:shadow-extruded transition-all"
        >
          Switch to {otherId}
        </button>
      )}
    </div>
  )
}

// Grouped sidebar IA. Each group is either a single leaf (Dashboard) or a
// section with children. Groups expand automatically when one of their
// children is the active route; collapse state otherwise persists in
// localStorage.
type NavLeaf = { path: string; label: string; icon?: any }
type NavGroup = { id: string; label: string; icon?: any; children: NavLeaf[] }
type NavEntry = NavLeaf | NavGroup

const NAV_GROUPS: NavEntry[] = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  {
    id: 'decisions',
    label: 'Decisions',
    icon: LineChartIcon,
    children: [
      { path: '/macro', label: 'Macro' },
      { path: '/predictions', label: 'Predictions' },
      { path: '/motion', label: 'Motion' },
    ],
  },
  {
    id: 'admin',
    label: 'Admin',
    icon: Zap,
    children: [
      { path: '/watchlist', label: 'Watchlist' },
      { path: '/schedule', label: 'Schedule' },
      { path: '/health', label: 'Health' },
    ],
  },
  { path: '/docs', label: 'Docs', icon: BookOpen },
]

function isLeaf(e: NavEntry): e is NavLeaf {
  return (e as NavLeaf).path !== undefined
}

function pathMatches(pathname: string, target: string): boolean {
  if (target === '/') return pathname === '/'
  return pathname === target || pathname.startsWith(target + '/')
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const location = useLocation()
  return (
    <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
      {NAV_GROUPS.map((entry) =>
        isLeaf(entry) ? (
          <NavLeafLink
            key={entry.path}
            leaf={entry}
            active={pathMatches(location.pathname, entry.path)}
            onNavigate={onNavigate}
          />
        ) : (
          <NavSection
            key={entry.id}
            group={entry}
            pathname={location.pathname}
            onNavigate={onNavigate}
          />
        ),
      )}
    </nav>
  )
}

function NavLeafLink({
  leaf,
  active,
  onNavigate,
  nested = false,
}: {
  leaf: NavLeaf
  active: boolean
  onNavigate?: () => void
  nested?: boolean
}) {
  const Icon = leaf.icon
  return (
    <Link
      to={leaf.path}
      onClick={onNavigate}
      className={[
        'flex items-center gap-3 rounded-2xl text-sm font-medium transition-all duration-200 ease-out min-h-[40px]',
        nested ? 'pl-10 pr-4 py-2' : 'px-4 py-3 min-h-[44px]',
        active
          ? 'shadow-inset-sm text-violet bg-background'
          : 'text-muted-foreground hover:text-foreground hover:shadow-extruded-sm',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2 focus-visible:ring-offset-background',
      ].join(' ')}
    >
      {Icon && <Icon className="h-4 w-4" />}
      {leaf.label}
    </Link>
  )
}

function NavSection({
  group,
  pathname,
  onNavigate,
}: {
  group: NavGroup
  pathname: string
  onNavigate?: () => void
}) {
  const sectionActive = useMemo(
    () => group.children.some((c) => pathMatches(pathname, c.path)),
    [group.children, pathname],
  )
  const storageKey = `sidebar.collapsed.${group.id}`
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    const stored = window.localStorage.getItem(storageKey)
    if (stored === '1') return true
    if (stored === '0') return false
    return false
  })

  // Auto-expand when navigating into a child route. Don't auto-collapse —
  // operator's manual collapse must stick.
  useEffect(() => {
    if (sectionActive) setCollapsed(false)
  }, [sectionActive])

  useEffect(() => {
    window.localStorage.setItem(storageKey, collapsed ? '1' : '0')
  }, [collapsed, storageKey])

  const Icon = group.icon
  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
        className={[
          'w-full flex items-center gap-3 px-4 py-3 rounded-2xl text-sm font-medium transition-all duration-200 ease-out min-h-[44px]',
          sectionActive
            ? 'text-foreground'
            : 'text-muted-foreground hover:text-foreground hover:shadow-extruded-sm',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        ].join(' ')}
      >
        {Icon && <Icon className="h-4 w-4" />}
        <span className="flex-1 text-left">{group.label}</span>
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5 opacity-60" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 opacity-60" />
        )}
      </button>
      {!collapsed && (
        <div className="space-y-0.5">
          {group.children.map((child) => (
            <NavLeafLink
              key={child.path}
              leaf={child}
              active={pathMatches(pathname, child.path)}
              onNavigate={onNavigate}
              nested
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  // Close mobile drawer on route change.
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  // Lock body scroll when drawer open.
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [mobileOpen])

  const breadcrumb =
    location.pathname === '/'
      ? 'Dashboard'
      : location.pathname.split('/').filter(Boolean).join(' / ')

  return (
    <div className="min-h-screen w-full bg-background text-foreground">
      {/* Desktop sidebar (hidden < md) */}
      <aside className="hidden md:flex fixed left-0 top-0 bottom-0 w-60 flex-col bg-background shadow-extruded z-40">
        <div className="h-16 flex items-center px-6">
          <h1 className="font-display font-extrabold text-xl tracking-tight">
            Kronos
          </h1>
        </div>
        <NavList />
      </aside>

      {/* Mobile drawer + overlay */}
      {mobileOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="fixed left-0 top-0 bottom-0 w-72 flex flex-col bg-background shadow-extruded z-50 md:hidden animate-in slide-in-from-left duration-200">
            <div className="h-16 flex items-center justify-between px-6">
              <h1 className="font-display font-extrabold text-xl tracking-tight">
                Kronos
              </h1>
              <button
                onClick={() => setMobileOpen(false)}
                className="h-10 w-10 flex items-center justify-center rounded-xl shadow-extruded-sm hover:shadow-extruded transition-all"
                aria-label="Close menu"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <NavList />
          </aside>
        </>
      )}

      {/* Main column */}
      <main className="md:ml-60 flex flex-col min-h-screen">
        {/* Topbar */}
        <header className="sticky top-0 h-16 bg-background/80 backdrop-blur-sm flex items-center justify-between px-4 md:px-8 z-30 shadow-[0_4px_12px_rgba(163,177,198,0.2)]">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileOpen(true)}
              className="md:hidden h-10 w-10 flex items-center justify-center rounded-xl shadow-extruded-sm hover:shadow-extruded transition-all"
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="font-medium text-sm text-muted-foreground capitalize truncate">
              {breadcrumb}
            </div>
          </div>
          <BackendToggle />
        </header>

        <BackendHealthBanner />

        {/* Content */}
        <div className="flex-1 p-4 md:p-8">
          <div className="max-w-7xl mx-auto">{children}</div>
        </div>
      </main>
    </div>
  )
}
