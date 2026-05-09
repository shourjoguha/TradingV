import { useQuery } from '@tanstack/react-query'
import { demoApi } from '../api'
import { ExternalLink } from 'lucide-react'

const GITHUB_URL =
  (import.meta.env.VITE_DEMO_GITHUB_URL as string | undefined) ??
  'https://github.com/shourjoguha/TradingV/tree/demo'
const CONTACT_URL =
  (import.meta.env.VITE_DEMO_CONTACT_URL as string | undefined) ??
  'mailto:guha.shourjo@gmail.com'

export function DemoBanner() {
  const { data: manifest } = useQuery({
    queryKey: ['demo', 'manifest'],
    queryFn: demoApi.manifest,
    staleTime: 60 * 60 * 1000,
  })

  const cutoff = manifest?.cutoff_date ?? '2026-05-09'

  return (
    <div className="sticky top-0 z-40 w-full bg-background/85 backdrop-blur-sm shadow-[0_4px_12px_rgba(163,177,198,0.2)]">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2 text-xs md:px-8">
        <div className="flex items-center gap-3 text-muted-foreground">
          <span className="rounded-full bg-violet/15 px-2 py-0.5 font-medium text-violet">
            DEMO
          </span>
          <span className="hidden sm:inline">
            Frozen snapshot · {cutoff} · sample data, no live feeds
          </span>
          <span className="sm:hidden">Frozen · {cutoff}</span>
        </div>
        <div className="flex items-center gap-3">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-muted-foreground transition-colors hover:text-violet"
          >
            GitHub <ExternalLink className="h-3 w-3" />
          </a>
          <a
            href={CONTACT_URL}
            className="inline-flex items-center gap-1 text-muted-foreground transition-colors hover:text-violet"
          >
            Request access
          </a>
        </div>
      </div>
    </div>
  )
}
