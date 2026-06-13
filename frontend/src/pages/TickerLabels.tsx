import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  useTickerLabels,
  useUpdateTickerLabels,
  useDeleteTickerLabel,
} from '../hooks/use-api'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { EmptyState } from '../components/common'
import { Label } from '../components/ui/label'
import { Skeleton } from '../components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '../components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { ArrowLeft, Trash2, Plus, Save } from 'lucide-react'
const CURATED_KEYS = [
  'sector',
  'capsize',
  'notes',
  'insider_buy',
  'hedge_funds',
  'planned_horizon',
]
export function TickerLabels() {
  const { symbol } = useParams<{
    symbol: string
  }>()
  const safeSymbol = symbol || ''
  const { data: labels, isLoading } = useTickerLabels(safeSymbol)
  const { mutate: updateLabels, isPending: isUpdating } =
    useUpdateTickerLabels(safeSymbol)
  const { mutate: deleteLabel } = useDeleteTickerLabel(safeSymbol)
  const [isAddOpen, setIsAddOpen] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newValType, setNewValType] = useState('string')
  const [newValStr, setNewValStr] = useState('')
  const handleAdd = () => {
    if (!newKey.trim()) return
    let parsedVal: any = newValStr
    if (newValType === 'boolean') {
      parsedVal = newValStr.toLowerCase() === 'true'
    } else if (newValType === 'number') {
      parsedVal = Number(newValStr)
    } else if (newValType === 'json') {
      try {
        parsedVal = JSON.parse(newValStr)
      } catch (e) {
        alert('Invalid JSON')
        return
      }
    }
    const updated = {
      ...(labels || {}),
      [newKey]: parsedVal,
    }
    updateLabels(updated, {
      onSuccess: () => {
        setIsAddOpen(false)
        setNewKey('')
        setNewValStr('')
      },
    })
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/watchlist">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">
            Labels: <span className="font-mono">{safeSymbol}</span>
          </h2>
          <p className="text-muted-foreground">
            Manage metadata and tags for this ticker.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <div>
            <CardTitle>Key-Value Pairs</CardTitle>
            <CardDescription>
              Used for filtering and analysis grouping.
            </CardDescription>
          </div>

          <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="h-4 w-4 mr-1" /> Add Label
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add Label to {safeSymbol}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label>Key</Label>
                  <div className="flex gap-2">
                    <Select value={newKey} onValueChange={setNewKey}>
                      <SelectTrigger className="w-[180px]">
                        <SelectValue placeholder="Select curated..." />
                      </SelectTrigger>
                      <SelectContent>
                        {CURATED_KEYS.map((k) => (
                          <SelectItem key={k} value={k}>
                            {k}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      placeholder="Or type custom key..."
                      value={newKey}
                      onChange={(e) => setNewKey(e.target.value)}
                      className="flex-1"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Value Type</Label>
                  <Select value={newValType} onValueChange={setNewValType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="string">String</SelectItem>
                      <SelectItem value="number">Number</SelectItem>
                      <SelectItem value="boolean">Boolean</SelectItem>
                      <SelectItem value="json">JSON Array/Object</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Value</Label>
                  {newValType === 'boolean' ? (
                    <Select value={newValStr} onValueChange={setNewValStr}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select true/false" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="true">True</SelectItem>
                        <SelectItem value="false">False</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      placeholder={
                        newValType === 'json' ? '["tech", "ai"]' : 'Value...'
                      }
                      value={newValStr}
                      onChange={(e) => setNewValStr(e.target.value)}
                      className="font-mono"
                    />
                  )}
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsAddOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={handleAdd}
                  disabled={isUpdating || !newKey || !newValStr}
                >
                  Save Label
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : !labels || Object.keys(labels).length === 0 ? (
            <EmptyState
              title={`No labels for ${safeSymbol}`}
              description="Add a label below to start tagging this ticker."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[200px]">Key</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead className="text-right w-[100px]">
                    Actions
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(labels).map(([key, val]) => (
                  <TableRow key={key}>
                    <TableCell className="font-medium font-mono text-sm">
                      {key}
                    </TableCell>
                    <TableCell className="font-mono text-sm text-muted-foreground">
                      {typeof val === 'object'
                        ? JSON.stringify(val)
                        : String(val)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          if (confirm(`Delete label '${key}'?`)) {
                            deleteLabel(key)
                          }
                        }}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
