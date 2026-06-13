import { useState } from 'react'
import { Building2, FileText } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { TierTable } from '../components/the-street/TierTable'
import { Button } from '../components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from '../components/ui/dialog'
import { useStreetSnapshots, useVaultNode } from '../hooks/use-api'
import { InfoBubble } from '../components/common'

/**
 * The Street — universe view of smart-money snapshots stored under
 * `<vault>/The Street/snapshots/`.
 *
 * 2026-05-17 IA simplification: Ticker timeline tab removed (redundant
 * with the per-ticker view operators reach via the Ticker Hub link on
 * each tier row). With only two surviving views, the tab strip was also
 * removed — latest tiers are the default page body, snapshot browse
 * moves to a button-triggered modal at 80vw/80vh w/ a dropdown picker
 * + inline rendered markdown (minimal gap between picker and content).
 */
export function TheStreet() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
          <Building2 className="h-6 w-6 text-primary" />
          The Street
          <InfoBubble
            label="About The Street"
            size={14}
            content="Smart-money snapshots — institutional 13Fs, insiders, politicians, options flow."
          />
        </h2>
        <SnapshotBrowserButton />
      </div>

      <div className="space-y-4">
        <TierTable tier={1} />
        <TierTable tier={2} />
        <TierTable tier={3} />
      </div>
    </div>
  )
}

/**
 * SnapshotBrowserButton — header-right button that opens a large modal
 * containing a snapshot dropdown and the rendered `_index.md` body.
 * Replaces the previous in-page tab + card pattern; reclaims vertical
 * canvas for the tier tables.
 */
function SnapshotBrowserButton() {
  const [open, setOpen] = useState(false)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const { data, isLoading } = useStreetSnapshots()
  const items = data?.items ?? []
  const node = useVaultNode(selectedPath)

  // Auto-pick the most-recent snapshot when the modal first opens (and
  // nothing is yet selected) so the operator lands on content, not an
  // empty body.
  if (open && !selectedPath && items.length > 0) {
    setSelectedPath(items[0].vault_path)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <FileText className="h-4 w-4 mr-2" />
          Snapshot
        </Button>
      </DialogTrigger>
      <DialogContent
        className="max-w-none w-[80vw] h-[80vh] flex flex-col p-5 gap-2"
      >
        <DialogTitle className="sr-only">Snapshot browser</DialogTitle>

        {/* Dropdown header row — minimal gap to body per operator audit. */}
        <div className="flex items-center gap-3 shrink-0">
          <label
            htmlFor="snapshot-select"
            className="text-xs text-muted-foreground shrink-0"
          >
            Snapshot
          </label>
          <select
            id="snapshot-select"
            value={selectedPath ?? ''}
            onChange={(e) => setSelectedPath(e.target.value || null)}
            className="bg-background rounded-xl px-3 py-2 text-sm font-mono shadow-inset-sm focus:outline-none focus:ring-2 focus:ring-primary"
            disabled={isLoading || items.length === 0}
          >
            {isLoading ? (
              <option>Loading…</option>
            ) : items.length === 0 ? (
              <option>No snapshots in vault</option>
            ) : (
              items.map((s) => (
                <option key={s.date} value={s.vault_path}>
                  {s.date}
                </option>
              ))
            )}
          </select>
          {selectedPath && (
            <span className="text-[11px] text-muted-foreground/70 font-mono truncate">
              {selectedPath}
            </span>
          )}
        </div>

        {/* Rendered _index.md body. Inset well below the dropdown w/
            minimal vertical gap (gap-2 = 8px on the parent flex). */}
        <div className="flex-1 min-h-0 overflow-auto rounded-2xl bg-background shadow-inset-sm p-4">
          {!selectedPath ? (
            <div className="text-sm text-muted-foreground italic">
              Pick a snapshot above.
            </div>
          ) : node.isLoading ? (
            <div className="text-sm text-muted-foreground italic">Loading…</div>
          ) : node.isError ? (
            <div className="text-sm text-muted-foreground italic">
              Vault indexer unreachable. Start it on port 8001.
            </div>
          ) : node.data ? (
            <div className="docs-article max-w-none text-foreground/90">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {node.data.body_md}
              </ReactMarkdown>
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}
