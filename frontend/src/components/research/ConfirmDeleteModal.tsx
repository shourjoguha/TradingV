import { Loader2, Trash2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Button } from '../ui/button'
import { useDeleteResearchQuery } from '../../hooks/use-api'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  queryId: string
  queryText: string
}

export function ConfirmDeleteModal({ open, onOpenChange, queryId, queryText }: Props) {
  const del = useDeleteResearchQuery()

  const onApply = () => {
    del.mutate(queryId, {
      onSuccess: () => onOpenChange(false),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Delete research query?</DialogTitle>
          <DialogDescription>
            Permanently removes the row from <code className="font-mono">research_queries</code>.
            The markdown archive in the vault is NOT removed.
          </DialogDescription>
        </DialogHeader>

        <div className="text-xs text-muted-foreground line-clamp-3 rounded-2xl shadow-inset-sm bg-background p-3 italic">
          {queryText}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={del.isPending}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onApply} disabled={del.isPending}>
            {del.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Deleting…
              </>
            ) : (
              <>
                <Trash2 className="h-4 w-4 mr-1.5" />
                Delete
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
