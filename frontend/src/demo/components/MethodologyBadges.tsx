import { ShieldCheck, GitBranch, BookOpen, Layers } from 'lucide-react'

const ITEMS = [
  {
    icon: ShieldCheck,
    title: 'Walk-forward validation',
    body: 'Predictions are evaluated only against actuals that came after them. No look-ahead, no peeking, no overfitting to the past.',
  },
  {
    icon: Layers,
    title: 'Per-rule attribution',
    body: 'Every closed trade rolls back to the rule that produced its opportunity. A rule with high hit-rate but tiny edge ranks below a rare, high-magnitude one.',
  },
  {
    icon: GitBranch,
    title: 'Drift detector running',
    body: 'When recent MAPE on any (ticker, horizon) pair exceeds threshold × all-time MAPE, the system flags itself before the operator notices.',
  },
  {
    icon: BookOpen,
    title: 'Open source',
    body: 'Demo branch is public on GitHub. Fork the repo, audit the source, run the patterns on any data. The honest demo is the only kind worth shipping.',
  },
] as const

export function MethodologyBadges() {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {ITEMS.map((it) => (
        <div
          key={it.title}
          className="flex items-start gap-3 rounded-2xl bg-background p-4 shadow-extruded-sm"
        >
          <div className="rounded-xl bg-background p-2 shadow-inset-sm">
            <it.icon className="h-4 w-4 text-violet" />
          </div>
          <div>
            <p className="text-sm font-semibold">{it.title}</p>
            <p className="text-xs leading-relaxed text-muted-foreground">{it.body}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
