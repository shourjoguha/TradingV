import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { useAdminLoops } from '../../hooks/use-api'
import { ProcessRow } from './ProcessRow'
import { Skeleton } from '../ui/skeleton'

export function ProcessesTab() {
  const { data, isLoading, isError } = useAdminLoops({ refetchMs: 30_000 })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Processes</CardTitle>
        <CardDescription>
          Background loops with status and manual fire/abort. Auto-refreshes every 30s.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-24 w-full" />}
        {isError && (
          <div className="text-sm text-amber-600">
            Failed to load loops. The endpoint requires the laptop backend.
          </div>
        )}
        {data && (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Loop</th>
                  <th className="py-2 pr-3">State</th>
                  <th className="py-2 pr-3">Last tick</th>
                  <th className="py-2 pr-3">Error</th>
                  <th className="py-2 pr-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <ProcessRow key={row.loop_id} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
