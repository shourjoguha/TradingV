import { useEffect, useState } from 'react'
import { Play, X, Maximize2, Minimize2, Video } from 'lucide-react'

interface WatchWalkthroughProps {
  /** YouTube video id. Null/empty -> renders the same button but the
   * modal shows a "video coming soon" placeholder instead of an iframe. */
  youtubeId?: string | null
  title: string
  durationSeconds?: number
}

/**
 * Big red YouTube-styled "Watch walkthrough" button + in-window modal.
 *
 * Modal sits at 70vw × 70vh by default (aspect-video constrained). A
 * fullscreen toggle expands it to fill the viewport. Click backdrop or
 * press Escape to close.
 */
/**
 * Until walkthrough videos are recorded, the button is hidden by default.
 * Flip `VITE_SHOW_WALKTHROUGH_PLACEHOLDERS=true` at build time to surface
 * the button with a "video coming soon" placeholder modal. Setting a real
 * youtubeId always wins — the env flag only affects the placeholder path.
 */
const SHOW_PLACEHOLDERS =
  import.meta.env.VITE_SHOW_WALKTHROUGH_PLACEHOLDERS === 'true'

export function WatchWalkthrough({
  youtubeId,
  title,
  durationSeconds = 60,
}: WatchWalkthroughProps) {
  const [open, setOpen] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)

  // Hide entirely when no video is wired and placeholder mode is off.
  if (!youtubeId && !SHOW_PLACEHOLDERS) return null

  // Close on Escape; lock body scroll while open.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (fullscreen) setFullscreen(false)
        else setOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [open, fullscreen])

  const mins = Math.floor(durationSeconds / 60)
  const secs = (durationSeconds % 60).toString().padStart(2, '0')
  const durationLabel = mins > 0 ? `${mins}:${secs}` : `${secs}s`

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="group inline-flex items-center gap-2.5 rounded-full bg-[#FF0000] px-4 py-2 text-sm font-semibold text-white shadow-extruded-sm transition-all hover:bg-[#cc0000] hover:shadow-extruded active:shadow-inset-sm"
        aria-label={`Watch walkthrough: ${title}`}
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white/20 transition-all group-hover:bg-white/30">
          <Play className="h-3 w-3 fill-white text-white" />
        </span>
        <span>Watch walkthrough</span>
        <span className="hidden rounded-full bg-black/20 px-2 py-0.5 text-[10px] font-medium tabular-nums sm:inline">
          {durationLabel}
        </span>
      </button>

      {open && (
        <Modal
          youtubeId={youtubeId ?? null}
          title={title}
          durationSeconds={durationSeconds}
          fullscreen={fullscreen}
          onToggleFullscreen={() => setFullscreen((v) => !v)}
          onClose={() => {
            setFullscreen(false)
            setOpen(false)
          }}
        />
      )}
    </>
  )
}

interface ModalProps {
  youtubeId: string | null
  title: string
  durationSeconds: number
  fullscreen: boolean
  onToggleFullscreen: () => void
  onClose: () => void
}

function Modal({
  youtubeId,
  title,
  durationSeconds,
  fullscreen,
  onToggleFullscreen,
  onClose,
}: ModalProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-0 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`relative flex flex-col overflow-hidden rounded-2xl bg-zinc-950 shadow-extruded transition-all ${
          fullscreen
            ? 'h-screen w-screen rounded-none'
            : 'h-[70vh] max-h-[70vh] w-[70vw] max-w-[70vw]'
        }`}
        style={fullscreen ? undefined : { aspectRatio: '16 / 9' }}
      >
        {/* Top control bar */}
        <div className="flex items-center justify-between gap-3 border-b border-white/10 bg-zinc-950/80 px-4 py-2 backdrop-blur-sm">
          <div className="flex items-center gap-2 truncate text-sm font-medium text-white">
            <Video className="h-4 w-4 text-[#FF0000]" />
            <span className="truncate">{title}</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onToggleFullscreen}
              className="rounded-md p-1.5 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
              aria-label={fullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            >
              {fullscreen ? (
                <Minimize2 className="h-4 w-4" />
              ) : (
                <Maximize2 className="h-4 w-4" />
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Video / placeholder */}
        <div className="relative flex-1 bg-black">
          {youtubeId ? (
            <iframe
              src={`https://www.youtube.com/embed/${youtubeId}?autoplay=1&rel=0`}
              title={title}
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
              allowFullScreen
              className="absolute inset-0 h-full w-full"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center p-8 text-center">
              <div className="space-y-3">
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#FF0000]/20">
                  <Video className="h-8 w-8 text-[#FF0000]" />
                </div>
                <p className="text-base font-semibold text-white">{title}</p>
                <p className="text-sm text-white/60">
                  Walkthrough video is being recorded — check back soon.
                </p>
                <p className="text-xs text-white/40">
                  Estimated runtime: {Math.floor(durationSeconds / 60)}:
                  {(durationSeconds % 60).toString().padStart(2, '0')}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
