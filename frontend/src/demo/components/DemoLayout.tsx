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
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <DemoBanner />
      <div className="mx-auto flex max-w-7xl gap-6 px-4 py-6">
        <aside className="hidden w-48 shrink-0 md:block">
          <div className="sticky top-16 space-y-1">
            <h1 className="mb-3 px-3 text-lg font-semibold tracking-tight text-violet">
              TradingView
            </h1>
            <nav className="flex flex-col gap-1">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={'end' in item ? item.end : false}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-md px-3 py-2 text-sm transition ${
                      isActive
                        ? 'bg-violet/15 text-violet'
                        : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100'
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
                  `whitespace-nowrap rounded-md px-3 py-1.5 text-xs transition ${
                    isActive
                      ? 'bg-violet/15 text-violet'
                      : 'bg-zinc-900 text-zinc-400'
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
      <footer className="border-t border-zinc-800 py-6 text-center text-xs text-zinc-500">
        Public demo · all data frozen · no live feeds, no model inference
      </footer>
    </div>
  )
}
