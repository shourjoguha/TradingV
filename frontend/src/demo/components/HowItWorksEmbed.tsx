import { useState } from 'react'
import { Play, Video } from 'lucide-react'

interface HowItWorksEmbedProps {
  /** YouTube video id, or null for placeholder. */
  youtubeId?: string | null
  title: string
  durationSeconds?: number
}

/**
 * Lazy-loaded "Watch how it works" thumbnail. When `youtubeId` is null
 * (default until the operator records the videos), shows a styled
 * placeholder instead of a broken iframe.
 */
export function HowItWorksEmbed({
  youtubeId,
  title,
  durationSeconds,
}: HowItWorksEmbedProps) {
  const [active, setActive] = useState(false)

  if (!youtubeId) {
    return (
      <div className="flex aspect-video w-full items-center justify-center rounded-lg border border-dashed border-zinc-800 bg-zinc-900/40 text-center">
        <div className="flex flex-col items-center gap-2 px-6 py-8">
          <Video className="h-8 w-8 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-300">{title}</p>
          <p className="text-xs text-zinc-500">Walkthrough video coming soon</p>
        </div>
      </div>
    )
  }

  if (!active) {
    return (
      <button
        type="button"
        onClick={() => setActive(true)}
        className="group relative aspect-video w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900"
      >
        <img
          src={`https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg`}
          alt={title}
          className="h-full w-full object-cover opacity-80 transition group-hover:opacity-100"
          loading="lazy"
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-violet/90 shadow-lg transition group-hover:scale-110">
            <Play className="h-6 w-6 fill-white text-white" />
          </div>
        </div>
        <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between text-xs text-white">
          <span className="rounded bg-black/60 px-2 py-0.5">{title}</span>
          {durationSeconds && (
            <span className="rounded bg-black/60 px-2 py-0.5">
              {Math.floor(durationSeconds / 60)}:
              {(durationSeconds % 60).toString().padStart(2, '0')}
            </span>
          )}
        </div>
      </button>
    )
  }

  return (
    <iframe
      src={`https://www.youtube.com/embed/${youtubeId}?autoplay=1&rel=0`}
      title={title}
      allow="autoplay; encrypted-media; picture-in-picture"
      allowFullScreen
      className="aspect-video w-full rounded-lg border border-zinc-800"
    />
  )
}
