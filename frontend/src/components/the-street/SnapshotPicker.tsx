import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useStreetSnapshots, useVaultNode } from '../../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'

export function SnapshotPicker() {
  const { data, isLoading } = useStreetSnapshots()
  const items = data?.items ?? []
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const node = useVaultNode(selectedPath)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Snapshot browser</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="text-xs text-muted-foreground italic">Loading…</div>
        ) : items.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No snapshots in vault yet.
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {items.map((s) => (
              <button
                key={s.date}
                type="button"
                onClick={() => setSelectedPath(s.vault_path)}
                className={`px-3 py-1.5 rounded-2xl text-xs font-mono shadow-extruded-sm hover:shadow-extruded transition-all ${
                  selectedPath === s.vault_path
                    ? 'bg-violet text-white'
                    : ''
                }`}
              >
                {s.date}
              </button>
            ))}
          </div>
        )}
        {selectedPath && (
          <div className="rounded-2xl shadow-inset-sm bg-background p-4 space-y-2">
            <Badge variant="outline" className="text-[10px]">
              {selectedPath}
            </Badge>
            {node.isLoading ? (
              <div className="text-xs text-muted-foreground italic">Loading…</div>
            ) : node.isError ? (
              <div className="text-xs text-muted-foreground italic">
                Vault indexer unreachable. Start it on port 8001.
              </div>
            ) : node.data ? (
              <div className="prose prose-sm max-w-none text-foreground/90 leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {node.data.body_md}
                </ReactMarkdown>
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
