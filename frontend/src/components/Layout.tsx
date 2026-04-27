import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, List, Clock, TrendingUp, Grid3x3, FlaskConical,
  Activity, Target, Receipt, Menu, X,
} from 'lucide-react'
import { BackendToggle } from './BackendToggle'

const NAV = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/watchlist', label: 'Watchlist', icon: List },
  { path: '/schedule', label: 'Schedule', icon: Clock },
  { path: '/predictions/by-target', label: 'By Target', icon: TrendingUp },
  { path: '/predictions/by-horizon', label: 'By Horizon', icon: Grid3x3 },
  { path: '/accuracy', label: 'Accuracy', icon: Activity },
  { path: '/opportunities', label: 'Opportunities', icon: Target },
  { path: '/trades', label: 'Trades', icon: Receipt },
  { path: '/analysis', label: 'Analysis', icon: FlaskConical },
]

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const location = useLocation()
  return (
    <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-2">
      {NAV.map((item) => {
        const Icon = item.icon
        const isActive =
          location.pathname === item.path ||
          (item.path !== '/' && location.pathname.startsWith(item.path))
        return (
          <Link
            key={item.path}
            to={item.path}
            onClick={onNavigate}
            className={`flex items-center gap-3 px-4 py-3 rounded-2xl text-sm font-medium transition-all duration-200 ease-out min-h-[44px] ${
              isActive
                ? 'shadow-inset-sm text-violet bg-background'
                : 'text-muted-foreground hover:text-foreground hover:shadow-extruded-sm'
            } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2 focus-visible:ring-offset-background`}
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </Link>
        )
      })}
    </nav>
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

        {/* Content */}
        <div className="flex-1 p-4 md:p-8">
          <div className="max-w-7xl mx-auto">{children}</div>
        </div>
      </main>
    </div>
  )
}
