import { useState } from 'react'
import { Search } from 'lucide-react'
import { useStreetTicker } from '../../hooks/use-api'
import { TickerLink } from '../common/TickerLink'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Input } from '../ui/input'
import { Badge } from '../ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table'

export function TickerTimeline() {
  const [input, setInput] = useState('')
  const [submitted, setSubmitted] = useState<string>('')
  const { data, isLoading } = useStreetTicker(submitted || null)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Search className="h-4 w-4 text-violet" />
          Ticker timeline
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            setSubmitted(input.trim().toUpperCase())
          }}
          className="flex items-center gap-2"
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ticker (e.g. META)"
            className="font-mono uppercase max-w-[12rem]"
          />
        </form>
        {submitted && (
          <>
            {isLoading ? (
              <div className="text-xs text-muted-foreground italic">Loading…</div>
            ) : !data || data.items.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">
                No snapshot mentions {submitted}.
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead className="text-right">Channels</TableHead>
                    <TableHead className="text-right">Bil/TB/Ins/Pol/Opt</TableHead>
                    <TableHead className="text-right">Signals</TableHead>
                    <TableHead>ETF</TableHead>
                    <TableHead>Notable</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((r) => (
                    <TableRow key={r.date}>
                      <TableCell className="font-mono">{r.date}</TableCell>
                      <TableCell className="text-right font-mono">
                        {r.channels}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {r.billionaires}/{r.trailblazers}/{r.insiders}/
                        {r.politicians}/{r.options_bullish}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {r.total_signals}
                      </TableCell>
                      <TableCell>{r.etf ? 'Y' : ''}</TableCell>
                      <TableCell className="text-xs text-muted-foreground line-clamp-1 max-w-[20rem]">
                        {r.notable}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {data && data.items.length > 0 && (
              <div className="text-xs">
                <Badge variant="outline">Open Ticker Hub</Badge>{' '}
                <TickerLink symbol={submitted} className="ml-1" />
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
