import { AlertTriangle, Camera } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card, CardContent } from '../ui/card'
import { Button } from '../ui/button'
import type { TickerContextStatus } from '../../lib/types'

interface ContextNeededBannerProps {
  contextCheck: TickerContextStatus[]
  onSkip: () => void
}

export function ContextNeededBanner({
  contextCheck,
  onSkip,
}: ContextNeededBannerProps) {
  const missing = contextCheck.filter((c) => c.needs_context)
  if (missing.length === 0) return null
  return (
    <Card className="border-warning-bg bg-warning-bg/20">
      <CardContent className="p-4 flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-warning-fg mt-0.5 shrink-0" />
        <div className="flex-1">
          <div className="font-medium text-sm">Context needed before research</div>
          <p className="text-xs text-muted-foreground mt-1">
            One or more bundled hypotheses require recent TV context (last 7d).
            Missing for:{' '}
            {missing.map((m) => (
              <code key={m.ticker} className="mx-1 font-mono">
                {m.ticker}
              </code>
            ))}
          </p>
          <div className="flex gap-2 mt-3 flex-wrap">
            {missing.map((m) => (
              <Button asChild key={m.ticker} size="sm" variant="outline" className="gap-2">
                <Link to={`/tv-context/${m.ticker}`}>
                  <Camera className="h-3 w-3" /> Attach for {m.ticker}
                </Link>
              </Button>
            ))}
            <Button size="sm" variant="ghost" onClick={onSkip}>
              Skip and proceed
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
