/**
 * Top-10 holdings per sector ETF, hardcoded.
 *
 * Why hardcoded: SSGA publishes monthly CSVs; the top-10 doesn't churn
 * weekly. Operator-curated map is faster than an ingestion pipeline,
 * and easy to keep in sync with a quarterly review. If a holding drops
 * out of the top-10 between reviews, the worst case is the drill-in
 * shows a slightly stale name — non-critical.
 *
 * Last reviewed: 2026-05-01. Next review: see backlog.md "Re-evaluate
 * active hypotheses" (same cadence works here too).
 *
 * Source: SSGA holdings pages for each `/etf/<symbol>` (US-listed
 * SPDR sector ETFs). Coalesced down to top-10 by weight.
 */

export const SECTOR_HOLDINGS: Record<string, string[]> = {
  XLK: ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'AMD', 'CSCO', 'ACN'],
  XLF: ['BRK-B', 'JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'AXP', 'MS', 'BLK'],
  XLE: ['XOM', 'CVX', 'COP', 'EOG', 'WMB', 'PSX', 'OKE', 'SLB', 'MPC', 'KMI'],
  XLV: ['LLY', 'JNJ', 'UNH', 'ABBV', 'MRK', 'TMO', 'ABT', 'PFE', 'DHR', 'AMGN'],
  XLI: ['GE', 'CAT', 'RTX', 'UNP', 'HON', 'BA', 'ETN', 'LMT', 'UPS', 'DE'],
  XLP: ['COST', 'PG', 'WMT', 'KO', 'PEP', 'PM', 'MO', 'MDLZ', 'CL', 'TGT'],
  XLY: ['AMZN', 'TSLA', 'HD', 'MCD', 'BKNG', 'TJX', 'SBUX', 'NKE', 'LOW', 'ABNB'],
  XLU: ['NEE', 'SO', 'DUK', 'CEG', 'AEP', 'SRE', 'D', 'EXC', 'XEL', 'PCG'],
  XLB: ['LIN', 'SHW', 'ECL', 'APD', 'FCX', 'NEM', 'CTVA', 'DOW', 'NUE', 'PPG'],
}
