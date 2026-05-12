import { Link } from 'react-router-dom'
import { ReactNode } from 'react'
import { ExternalLink } from 'lucide-react'

interface Props {
  symbol: string
  className?: string
  children?: ReactNode
  /** When true, render as a chip-style pill (rounded shadow). */
  chip?: boolean
  /** Suppress the TradingView.com chart link (default: shown). */
  hideChartLink?: boolean
}

/**
 * Standard ticker link.
 *
 * Two affordances:
 *   1. The symbol text routes internally to the Ticker Hub at
 *      `/ticker/SYM` so every ticker mention in the UI lands on the
 *      single-screen synthesis page.
 *   2. A small external-link arrow opens the symbol's TradingView.com
 *      chart in a new tab — operator's preferred workflow when they
 *      want to draw on the chart side-by-side with the app data.
 *
 * Pass `hideChartLink` for terse tabular contexts (e.g. dense rows that
 * already have other affordances).
 */
export function TickerLink({
  symbol,
  className,
  children,
  chip = false,
  hideChartLink = false,
}: Props) {
  const upper = symbol?.toUpperCase() ?? ''
  if (!upper) return null
  const base = chip
    ? 'inline-flex items-center px-2 py-0.5 rounded-full shadow-extruded-sm font-mono text-xs hover:shadow-extruded transition-all'
    : 'font-mono hover:text-violet hover:underline'
  return (
    <span className="inline-flex items-center gap-1">
      <Link to={`/ticker/${upper}`} className={`${base} ${className ?? ''}`.trim()}>
        {children ?? upper}
      </Link>
      {!hideChartLink && (
        <a
          href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(upper)}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          aria-label={`Open ${upper} on TradingView.com`}
          className="inline-flex items-center text-muted-foreground hover:text-violet transition-colors"
        >
          <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </span>
  )
}
