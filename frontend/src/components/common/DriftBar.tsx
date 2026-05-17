/**
 * DriftBar — unified scalar-to-bar widget for drift_score (0..1).
 *
 * Replaces three drifted implementations:
 *   - components/today/RxStrip.tsx (w-12)
 *   - pages/RxFinance.tsx (w-16)
 *   - pages/RxFinanceDetail.tsx (text only)
 *
 * Thresholds (operator-tuned):
 *   < 0.40 → success (green) — quiet
 *   < 0.70 → warning (amber)  — meaningful
 *   ≥ 0.70 → danger  (coral)  — urgent
 *
 * Sizing:
 *   sm  → bar w-12 h-1.5 (Today strip, dense tables)
 *   md  → bar w-16 h-1.5 (default; main rec list)
 *   lg  → bar w-24 h-2   (detail-page emphasis)
 */
import { useMemo } from 'react'

export type DriftBarSize = 'sm' | 'md' | 'lg'

const SIZE_TO_CLASSES: Record<DriftBarSize, { bar: string; label: string }> = {
  sm: { bar: 'h-1.5 w-12', label: 'text-[10px]' },
  md: { bar: 'h-1.5 w-16', label: 'text-xs' },
  lg: { bar: 'h-2 w-24', label: 'text-sm' },
}

function colorFor(score: number): string {
  if (score >= 0.70) return 'bg-danger'
  if (score >= 0.40) return 'bg-warning'
  return 'bg-success'
}

export function DriftBar({
  score,
  size = 'md',
  hideLabel = false,
}: {
  score: number | null | undefined
  size?: DriftBarSize
  hideLabel?: boolean
}) {
  const styles = SIZE_TO_CLASSES[size]
  const safe = useMemo(() => {
    if (score == null || !isFinite(score)) return null
    return Math.max(0, Math.min(1, score))
  }, [score])
  if (safe == null) {
    return <span className={`text-muted-foreground ${styles.label}`}>—</span>
  }
  const pct = safe * 100
  return (
    <div className="inline-flex items-center gap-2">
      <div
        className={`${styles.bar} rounded-full bg-muted overflow-hidden shrink-0`}
        role="meter"
        aria-valuenow={Number(safe.toFixed(2))}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-label={`drift score ${safe.toFixed(2)}`}
      >
        <div className={`h-full ${colorFor(safe)}`} style={{ width: `${pct}%` }} />
      </div>
      {!hideLabel && (
        <span className={`text-muted-foreground tabular-nums ${styles.label}`}>
          {safe.toFixed(2)}
        </span>
      )}
    </div>
  )
}
