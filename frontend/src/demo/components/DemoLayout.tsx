import { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, BarChart3, Activity, Info } from 'lucide-react'
import { DemoBanner } from './DemoBanner'

const NAV = [
  { to: '/', label: 'Today', icon: LayoutDashboard, end: true },
  { to: '/predictions', label: 'Predictions', icon: BarChart3 },
  { to: '/motion', label: 'Motion', icon: Activity },
  { to: '/about', label: 'About', icon: Info },
] as const

interface DemoLayoutProps {
  children: ReactNode
}

export function DemoLayout({ children }: DemoLayoutProps) {
  return (
    <div className="min-h-screen w-full bg-background text-foreground">
      <DemoBanner />
      <div className="mx-auto flex max-w-7xl gap-6 px-4 py-6 md:px-8">
        <aside className="hidden w-52 shrink-0 md:block">
          <div className="sticky top-20 space-y-3">
            <h1 className="px-3 font-display text-xl font-extrabold tracking-tight">
              Kronos
            </h1>
            <nav className="space-y-1">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={'end' in item ? item.end : false}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-2xl px-3 py-2 text-sm transition-all ${
                      isActive
                        ? 'shadow-inset-sm text-violet bg-background'
                        : 'text-muted-foreground hover:text-foreground'
                    }`
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </aside>

        <main className="min-w-0 flex-1 space-y-6">
          <nav className="flex gap-2 overflow-x-auto md:hidden">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={'end' in item ? item.end : false}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-2xl px-3 py-1.5 text-xs transition-all ${
                    isActive
                      ? 'shadow-inset-sm text-violet'
                      : 'shadow-extruded-sm text-muted-foreground'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          {children}
        </main>
      </div>
      <footer className="py-8 text-center text-xs text-muted-foreground">
        Public demo · all data frozen · no live feeds, no model inference
      </footer>
    </div>
  )
}
