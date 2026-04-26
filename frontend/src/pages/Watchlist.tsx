import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useWatchlist,
  useAddTicker,
  useBulkAddTickers,
  useDeleteTicker,
} from '../hooks/use-api'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Badge } from '../components/ui/badge'
import { Skeleton } from '../components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '../components/ui/dialog'
import { Textarea } from '../components/ui/textarea'
import { Trash2, Plus, Tags } from 'lucide-react'
export function Watchlist() {
  const [newSymbol, setNewSymbol] = useState('')
  const [bulkSymbols, setBulkSymbols] = useState('')
  const [isBulkOpen, setIsBulkOpen] = useState(false)
  const { data, isLoading } = useWatchlist({
    limit: 100,
  })
  const { mutate: addTicker, isPending: isAdding } = useAddTicker()
  const { mutate: bulkAdd, isPending: isBulkAdding } = useBulkAddTickers()
  const { mutate: deleteTicker } = useDeleteTicker()
  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newSymbol.trim()) return
    addTicker(
      {
        symbol: newSymbol.trim().toUpperCase(),
      },
      {
        onSuccess: () => setNewSymbol(''),
      },
    )
  }
  const handleBulkAdd = () => {
    const symbols = bulkSymbols
      .split(/[\n,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean)
    if (symbols.length === 0) return
    bulkAdd(
      {
        symbols,
      },
      {
        onSuccess: () => {
          setBulkSymbols('')
          setIsBulkOpen(false)
        },
      },
    )
  }
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-heading font-semibold tracking-tight">
            Watchlist
          </h2>
          <p className="text-muted-foreground">
            Manage tickers for prediction and analysis.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <CardTitle>Tickers</CardTitle>
          <div className="flex items-center gap-2">
            <form onSubmit={handleAdd} className="flex items-center gap-2">
              <Input
                placeholder="AAPL"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value)}
                className="w-32 uppercase font-mono"
              />
              <Button
                type="submit"
                disabled={isAdding || !newSymbol.trim()}
                size="sm"
              >
                <Plus className="h-4 w-4 mr-1" /> Add
              </Button>
            </form>

            <Dialog open={isBulkOpen} onOpenChange={setIsBulkOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm">
                  Bulk Add
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Bulk Add Tickers</DialogTitle>
                </DialogHeader>
                <div className="py-4">
                  <Textarea
                    placeholder="AAPL, MSFT&#10;GOOGL&#10;AMZN"
                    value={bulkSymbols}
                    onChange={(e) => setBulkSymbols(e.target.value)}
                    className="min-h-[150px] font-mono"
                  />
                  <p className="text-xs text-muted-foreground mt-2">
                    Enter symbols separated by commas or newlines.
                  </p>
                </div>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setIsBulkOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleBulkAdd}
                    disabled={isBulkAdding || !bulkSymbols.trim()}
                  >
                    Add Tickers
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : data?.items && data.items.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Added At</TableHead>
                  <TableHead>Notes</TableHead>
                  <TableHead>Labels</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((item) => (
                  <TableRow key={item.symbol}>
                    <TableCell className="font-mono font-bold">
                      {item.symbol}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {new Date(item.added_at).toISOString().split('T')[0]}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {item.notes || '-'}
                    </TableCell>
                    <TableCell>
                      <Link to={`/tickers/${item.symbol}/labels`}>
                        <Badge
                          variant="secondary"
                          className="hover:bg-secondary/80 cursor-pointer"
                        >
                          <Tags className="h-3 w-3 mr-1" /> Edit Labels
                        </Badge>
                      </Link>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          if (
                            confirm(`Remove ${item.symbol} from watchlist?`)
                          ) {
                            deleteTicker(item.symbol)
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
          ) : (
            <div className="text-center py-12 text-sm text-muted-foreground border border-dashed rounded-lg">
              No tickers in watchlist. Add some to get started.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
