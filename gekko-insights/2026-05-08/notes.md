# Methodology — 2026-05-08

## Filters applied

- **Insiders**: time=90D, value=$100k+. Filtered client-side to last ~60 days (today minus 2mo).
- **Politicians**: time=90D, value=$100k+. Page only shows BUYS — title is 'Politician Purchases'. 8 rows total at $100K+ in 90d window.
- **Trailblazers**: 51 funds, click each card to load right-pane portfolio. Filter rows where status badge is `▲ Added`, `New`, `Added`, or `Increased`. 5 funds (12 West, Praesidium, Tekne, Rangeley, Crosslink) returned empty due to React click-toggle race; data captured otherwise.
- **Billionaires**: 32 named billionaires, same click-iter pattern. Most billionaire portfolios show no Q4 2025 changes (held flat). Only 6 had Added/New: Buffett, Laffont, Gayner, Sundheim, Tepper, Cooperman.
- **Options**: time=90D (page returned ~10d due to render limits), signal=Bullish, conviction=50+. Treats BULLISH options flow as 'buy' signal for underlying.
- **Whales**: SKIPPED. Polymarket prediction-market trades (sports/esports/politics outcomes) — not stock tickers.

## Caveats

- Politicians disclose buy AMOUNT as a **range** (e.g. $100,001–$250,000), not a precise value. The $100k+ filter applies to the lower bound.
- Politicians have ~30-45 day disclosure lag. TRADED date column is when the trade happened; DISCLOSED is when filed. Used DISCLOSED for the time filter to align with what's visible.
- Options signals reflect 30-day rolling smart-money options flow snapshot, not literal share buys.
- Trailblazers/Billionaires data is from Q4 2025 13F filings — quarterly cadence, lags up to 45 days. Some Trailblazers show Q2 2025 (Repertoire), older.
- ETF-tagged tickers in aggregate (IVV, SPY, QQQ, GLD, etc.) are flagged in `ETF?` column. Often dominate Tier 1 due to broad allocation, not single-name conviction.

## Folder structure

```
gekko-insights/
  2026-05-08/
    raw/                # raw scrape data per channel
      insiders.tsv
      politicians.tsv
      trailblazers.json
      billionaires.json
      options_bullish.tsv
    aggregate/
      multi-channel-tickers.tsv  # full table — every ticker appearing in 2+ channels
      multi-channel-tickers.json # same as JSON for programmatic consumption
      tier-summary.md            # tier 1/2/3 markdown report
    notes.md            # this file
```

## How to query

```bash
# Top 30 by channel count (excluding ETFs)
awk -F'\t' 'NR>1 && $2!="Y" {print $0}' aggregate/multi-channel-tickers.tsv | sort -t$'\t' -k8,8nr | head -30

# Tier 1 only
awk -F'\t' 'NR>1 && $8>=4 && $2!="Y"' aggregate/multi-channel-tickers.tsv

# Tickers with politician buys
awk -F'\t' 'NR>1 && $6>0' aggregate/multi-channel-tickers.tsv
```
