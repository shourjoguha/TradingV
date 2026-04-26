import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, List, Clock, TrendingUp, Grid3x3, FlaskConical,
} from 'lucide-react'
import { BackendToggle } from './BackendToggle'

const NAV = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/watchlist', label: 'Watchlist', icon: List },
  { path: '/schedule', label: 'Schedule', icon: Clock },
  { path: '/predictions/by-target', label: 'By Target', icon: TrendingUp },
  { path: '/predictions/by-horizon', label: 'By Horizon', icon: Grid3x3 },
  { path: '/analysis', label: 'Analysis', icon: FlaskConical },
]

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  return (
    <div className="flex h-screen w-full bg-background text-foreground overflow-hidden">
      <aside className="w-56 border-r border-border bg-card flex flex-col">
        <div className="h-14 flex items-center px-6 border-b border-border">
          <h1 className="font-heading font-semibold tracking-tight">Kronos</h1>
        </div>
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          {NAV.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.path ||
              (item.path !== '/' && location.pathname.startsWith(item.path))
            return (
              <Link key={item.path} to={item.path}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}>
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            )
          })}
        </nav>
      </aside>
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-14 border-b border-border bg-background flex items-center justify-between px-6 shrink-0">
          <div className="font-medium text-sm text-muted-foreground capitalize">
            {location.pathname === '/' ? 'Dashboard'
              : location.pathname.split('/').filter(Boolean).join(' / ')}
          </div>
          <BackendToggle />
        </header>
        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-7xl mx-auto">{children}</div>
        </div>
      </main>
    </div>
  )
}
