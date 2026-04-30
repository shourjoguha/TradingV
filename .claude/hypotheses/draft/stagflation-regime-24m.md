---
name: "Stagflation regime — long real assets, defensive equity (24mo)"
slug: "stagflation-regime-24m"
parent_id: null
expected_dir: "regime_shift"
claim_type: "absolute_with_relative_signal"
primary_metric: "DFII10"                 # 10Y real yield — the cleanest stagflation tell
tracking_signal: "PPI/CPI"               # cost-push leading; signal hits the supply chain first
ttl_months: 24
ratios:
  # Inflation regime panel (the dedicated stagflation tracking surface)
  - "DFII10"                             # 10Y real yield (TIPS-implied)
  - "T5YIE"                              # 5Y inflation expectations (faster than 10Y)
  - "T10YIE"                             # 10Y inflation expectations (locked-in expectations)
  - "PPIACO"                             # producer prices (raw input)
  - "CPIAUCSL"                           # consumer prices (passed-through input)
  - "PPI/CPI"                            # ratio — pass-through pressure (computed via /v1/macro/ratio)
  - "DBC/SPY"                            # broad commodities vs equities
  # Cross-axis confirmers
  - "GC=F/SPY"                           # gold vs equity (debasement)
  - "CL=F/GC=F"                          # oil vs gold (energy-led inflation marker)
  - "MORTGAGE30US − WGS10YR"             # mortgage spread (financial-conditions stress)
  - "DX-Y.NYB"                           # USD regime — strong dollar disconfirms
  - "WALCL"                              # Fed balance sheet — liquidity context
invalidators:
  # Real yields turn meaningfully positive AND stay there → stagflation
  # narrative breaks (Volcker-style policy success).
  - "DFII10 > 2.5% sustained for 90 days"
  # Inflation expectations cool back toward target.
  - "T5YIE < 2.0% AND T10YIE < 2.0% sustained for 60 days"
  # Producer prices roll over (cost-push pressure dissipating).
  - "PPI/CPI 6-month rate of change < 0 for 90 days"
  # Strong USD regime returns — disinflation playbook wins, this thesis dies.
  - "DX-Y.NYB > 110 sustained for 60 days"
source_url: ""
created_at: 2026-05-01
---

# Stagflation regime — long real assets, defensive equity (24mo)

## Thesis (1-2 paragraphs)

The combination of (a) sticky inflation expectations un-anchored above
historical 2% target, (b) negative-to-low real yields, (c) cost-push pressure
in producer prices that hasn\'t fully passed through to consumers, and (d) a
USD regime that has rolled over from peak, produces a multi-year **stagflation
regime**: persistent inflation alongside stagnant real growth.

The bet is **not directional on equities** — it\'s on the *relative
performance* of asset classes within the regime: real assets (gold,
broad-commodities, energy producers, hard-asset-exposed EM) outperform
long-duration tech and consumer discretionary on a multi-year basis. Within
equities, defensive sectors (Staples, Utilities, Energy, Materials) outperform
cyclical and growth.

This is a regime-shift thesis with a 24-month TTL — long enough to capture
multiple Fed cycles + a recession-or-not test. The primary metric is **DFII10
(10Y real yield)** — when this stays meaningfully negative or barely positive
while breakevens stay elevated, the regime holds.

## Why now

- 5Y breakevens (T5YIE) running above 10Y breakevens (T10YIE) historically
  signals near-term inflation pressure that markets expect to fade — but
  recent prints suggest stickier-than-expected.
- PPI/CPI ratio elevated → cost-push pressure still in the supply chain;
  margins about to compress.
- USD (DXY) has rolled from cycle highs → opposite of the disinflationary
  strong-USD regime.
- Fed balance sheet stabilising (no aggressive QT), real yields can\'t rise
  much without breaking financing conditions (mortgage spread already wide).
- Commodity supercycle thesis (Costa, Druckenmiller framing) reinforces this:
  decade-long under-investment in mining / energy capex meets re-shored
  industrial demand.

## Confirming evidence (current)

- DFII10 trending sideways-to-down — real yields not rising despite nominal
  rate hikes (the canonical stagflation marker).
- 5Y breakevens elevated; spread between 5Y and 10Y breakevens widened.
- PPI/CPI ratio above 5-year average.
- Commodities/SPY (DBC/SPY) holding above its 200-day SMA.
- Gold/SPX in a multi-year breakout (cross-references the LatAm thesis).

## Invalidating conditions

See frontmatter. Four invalidators across three categories:

- **Real yields normalise** (DFII10 > 2.5% sustained) — Volcker-style policy
  success. Stagflation thesis broken.
- **Inflation expectations cool** (T5YIE + T10YIE < 2%) — disinflation wins.
- **Producer-price pass-through dissipates** (PPI/CPI 6mo RoC < 0) — cost-push
  pressure gone, regime shifts to standard cyclical.
- **USD super-strength returns** (DXY > 110) — disinflation playbook wins on
  the back of trade-weighted dollar, this thesis dies regardless of internals.

## Trade implication

If `confirming`:

- **Long bias:** broad commodities (DBC), energy producers, gold (GLD / GC=F),
  hard-asset-exposed EM (LatAm via ILF — cross-references
  [`latam-breakout-36m.md`](latam-breakout-36m.md)), defensive sectors (XLE,
  XLP, XLU, XLB).
- **Short / underweight:** long-duration growth (XLK ex-AI infrastructure,
  consumer discretionary XLY), zero-coupon Treasuries (TLT — the rate
  re-pricing hurts duration disproportionately).
- **Pair trades:** long XLE / short XLY; long DBC / short SPY.
- **Hedge:** TIPS for the inflation expression; gold for the debasement
  expression.

If `violated` via real-yield normalisation: rotate hard out of long-duration
hedges and into rate-cycle-end plays (long-duration Treasuries, growth equity
re-rating).

## Source / inspiration

- Otavio Costa (Crescat Capital) — debasement + commodity supercycle thesis.
- Stanley Druckenmiller — liquidity + USD regime framing.
- Howard Marks "Sea Change" memo — multi-decade regime shift framing.

This thesis intersects with [`latam-breakout-36m.md`](latam-breakout-36m.md)
(commodity-cycle tailwind) and [`btc-rally-24m.md`](btc-rally-24m.md)
(USD-debasement tailwind). All three share the underlying claim that the
post-2008 disinflationary regime is over.
