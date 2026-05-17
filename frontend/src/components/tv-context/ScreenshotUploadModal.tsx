import { useEffect, useRef, useState } from 'react'
import { ImagePlus, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Textarea } from '../ui/textarea'
import { Switch } from '../ui/switch'
import {
  useExtractScreenshotTicker,
  useIngestTVScreenshot,
  type ScreenshotTickerCandidate,
} from '../../hooks/use-api'
import { Sparkles } from 'lucide-react'

interface ScreenshotUploadModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultTicker?: string
  hypothesisId?: string
}

const ESTIMATED_COST_USD = 0.012  // ~1024px chart, Claude Sonnet 4.6 vision

export function ScreenshotUploadModal({
  open,
  onOpenChange,
  defaultTicker,
  hypothesisId,
}: ScreenshotUploadModalProps) {
  const [ticker, setTicker] = useState(defaultTicker ?? '')
  const [note, setNote] = useState('')
  const [visionEnabled, setVisionEnabled] = useState(true)
  const [file, setFile] = useState<File | Blob | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [autoFilledTicker, setAutoFilledTicker] = useState<string | null>(null)
  const [hintCandidates, setHintCandidates] = useState<ScreenshotTickerCandidate[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const ingest = useIngestTVScreenshot()
  const extractTicker = useExtractScreenshotTicker()

  useEffect(() => {
    if (open && defaultTicker) setTicker(defaultTicker)
  }, [open, defaultTicker])

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const handleFile = (f: File | Blob | null) => {
    setFile(f)
    setAutoFilledTicker(null)
    setHintCandidates([])
    if (!f) return
    // Best-effort OCR ticker extraction. Only prefill when the top
    // candidate is in the operator's whitelist (roster ∪ boards ∪
    // The Street). Out-of-universe candidates become chip hints.
    extractTicker
      .mutateAsync({ file: f })
      .then((result) => {
        if (!result.ocr_used || result.candidates.length === 0) return
        const whitelistHit = result.candidates.find((c) => c.source === 'whitelist')
        if (whitelistHit && (defaultTicker == null || defaultTicker === '')) {
          setTicker(whitelistHit.ticker)
          setAutoFilledTicker(whitelistHit.ticker)
        }
        const hints = result.candidates
          .filter((c) => c.source === 'stoplist-passed')
          .slice(0, 4)
        setHintCandidates(hints)
      })
      .catch(() => {
        // Soft-fail: keep current ticker state, no hints.
      })
  }

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const dropped = e.dataTransfer.files?.[0]
    if (dropped) handleFile(dropped)
  }

  const onPaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    const item = Array.from(e.clipboardData.items).find((i) =>
      i.type.startsWith('image/'),
    )
    if (!item) return
    const blob = item.getAsFile()
    if (blob) handleFile(blob)
  }

  const reset = () => {
    setFile(null)
    setNote('')
    setAutoFilledTicker(null)
    setHintCandidates([])
  }

  const onSubmit = async () => {
    if (!file || !ticker.trim()) return
    try {
      await ingest.mutateAsync({
        file,
        ticker: ticker.trim().toUpperCase(),
        note: note.trim() || undefined,
        hypothesisId,
        visionEnabled,
      })
      reset()
      onOpenChange(false)
    } catch {
      // toast handled in mutation hook
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Add chart screenshot</DialogTitle>
          <DialogDescription>
            Drop / paste a TradingView chart for {ticker || '<ticker>'}. Stored
            in your vault sidecar markdown — no upload to TradingView.
          </DialogDescription>
        </DialogHeader>

        <div
          className="space-y-4"
          onPaste={onPaste}
          tabIndex={0}
          onClick={(e) => (e.currentTarget as HTMLDivElement).focus()}
        >
          <div>
            <div className="flex items-center justify-between">
              <Label htmlFor="ticker">Ticker</Label>
              {autoFilledTicker && autoFilledTicker === ticker.toUpperCase() && (
                <span className="inline-flex items-center gap-1 text-[10px] text-violet">
                  <Sparkles className="h-3 w-3" />
                  auto-detected from chart
                </span>
              )}
            </div>
            <Input
              id="ticker"
              value={ticker}
              onChange={(e) => {
                setTicker(e.target.value)
                if (autoFilledTicker && e.target.value.toUpperCase() !== autoFilledTicker) {
                  setAutoFilledTicker(null)
                }
              }}
              placeholder="AAPL"
              className="mt-1"
            />
            {hintCandidates.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] text-muted-foreground">
                  Also seen in chart:
                </span>
                {hintCandidates.map((c) => (
                  <button
                    key={c.ticker}
                    type="button"
                    onClick={() => setTicker(c.ticker)}
                    className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-mono hover:bg-accent transition-colors"
                  >
                    {c.ticker}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div
            className="border-2 border-dashed rounded-xl p-6 text-center transition-colors hover:bg-accent/40 cursor-pointer"
            onDragOver={(e) => e.preventDefault()}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            {previewUrl ? (
              <div className="relative">
                <img
                  src={previewUrl}
                  alt="preview"
                  className="max-h-64 mx-auto rounded shadow"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="absolute top-1 right-1"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleFile(null)
                  }}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ) : (
              <div className="text-muted-foreground text-sm space-y-2">
                <ImagePlus className="h-8 w-8 mx-auto opacity-50" />
                <p>Drag an image here, paste from clipboard, or click to choose</p>
                <p className="text-xs">PNG / JPG. Stored in vault.</p>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
            />
          </div>

          <div>
            <Label htmlFor="note">Caption (optional)</Label>
            <Textarea
              id="note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What's the setup? (skip if vision is enabled)"
              rows={3}
              className="mt-1"
            />
          </div>

          <div className="flex items-start gap-3 rounded-lg border p-3">
            <Switch
              id="vision"
              checked={visionEnabled}
              onCheckedChange={setVisionEnabled}
            />
            <div className="flex-1">
              <Label htmlFor="vision" className="cursor-pointer">
                Auto-summarize chart with Claude vision
              </Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Estimated cost: ~${ESTIMATED_COST_USD.toFixed(3)} per chart. Skip
                if you'll write a thorough caption.
              </p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={onSubmit}
            disabled={!file || !ticker.trim() || ingest.isPending}
          >
            {ingest.isPending ? 'Uploading…' : 'Save to vault'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
