import { ReactNode } from 'react'

interface HeroStatProps {
  /** Headline contrast — one short line, ~6-10 words. */
  headline: string
  /** Subhead, second person, present tense, ~12-18 words. */
  subhead: string
  /** The single big number(s) — keep tight. */
  primaryStat: ReactNode
  /** Trust badges along the bottom. */
  badges?: { label: string; tone?: 'authority' | 'neutral' }[]
  /** Single primary CTA. */
  cta?: { label: string; href?: string; onClick?: () => void }
  /** Optional walkthrough button slot — sits in the same row as the
   * headline, top right. Pass <WatchWalkthrough .../>. */
  walkthrough?: ReactNode
}

export function HeroStat({
  headline,
  subhead,
  primaryStat,
  badges,
  cta,
  walkthrough,
}: HeroStatProps) {
  return (
    <section className="rounded-2xl bg-background p-6 shadow-extruded md:p-8">
      {walkthrough && (
        <div className="mb-4 flex justify-end md:hidden">{walkthrough}</div>
      )}
      <div className="grid gap-6 md:grid-cols-[1fr_auto] md:items-start">
        <div className="space-y-3">
          <h2 className="font-display text-2xl font-bold tracking-tight md:text-3xl">
            {headline}
          </h2>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground md:text-base">
            {subhead}
          </p>
          {badges && badges.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {badges.map((b) => (
                <span
                  key={b.label}
                  className={`rounded-full px-3 py-1 text-[11px] font-medium tracking-tight shadow-extruded-sm ${
                    b.tone === 'authority' ? 'text-violet' : 'text-muted-foreground'
                  }`}
                >
                  {b.label}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-col items-start gap-3 md:items-end">
          {walkthrough && <div className="hidden md:block">{walkthrough}</div>}
          <div className="font-display text-3xl font-bold tabular-nums md:text-4xl">
            {primaryStat}
          </div>
          {cta && (
            <a
              href={cta.href}
              onClick={cta.onClick}
              className="rounded-2xl bg-violet px-5 py-2 text-sm font-medium text-white shadow-extruded-sm transition-all hover:shadow-extruded"
            >
              {cta.label}
            </a>
          )}
        </div>
      </div>
    </section>
  )
}
