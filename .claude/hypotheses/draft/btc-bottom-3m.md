---
name: "BTC bottom forms within 3 months"
slug: "btc-bottom-3m"
parent_id: null
expected_dir: "regime_shift"             # not directional yet — claim is about pattern formation
claim_type: "absolute"
primary_metric: "BTC-USD"
tracking_signal: "BTC-USD"               # absolute price; secondary watch on funding rates
ttl_months: 3
ratios:
  - "BTC-USD"
  - "BTC-USD/GC=F"                       # BTC vs gold (alternative-store-of-value regime)
  - "MSTR/BTC-USD"                       # MSTR-vs-BTC mNAV health proxy
  - "DX-Y.NYB"                           # USD inverse co-mover for BTC
  - "WALCL"                              # Fed BS — liquidity context
invalidators:
  # The bottom hasn't formed yet
  - "BTC-USD makes a new 12-month low after month 1 of this hypothesis"
  - "BTC-USD makes a lower-low at month 2 vs month 1"
  - "BTC-USD makes a lower-low at month 3 vs month 2"
  # Macro context turns hard against
  - "DX-Y.NYB > 110 sustained for 30 days during this 3mo window"
source_url: ""
created_at: 2026-04-30
---

# BTC bottom forms within 3 months

## Thesis (1-2 paragraphs)

Within the next 3 months, BTC prints a tradable bottom — defined as a higher-low
relative to the current drawdown leg, holding for ≥ 14 days, with bullish
divergence on momentum (RSI / MACD on weekly chart). This is a **precondition
hypothesis** for [`btc-rally-24m.md`](btc-rally-24m.md): if no bottom forms in
this window, the 24-month rally thesis is auto-cancelled.

The claim is *not* directional yet. We are not betting BTC goes up over 3
months — we are betting it stops going **down**. Direction belongs to the
24mo stage.

## Why now

- Halving was April 2024; cycle bottoms historically form 12-18 months pre-halving
  and ~12 months post-halving — we're inside the post-halving accumulation
  window.
- ETF flows turned net-positive after the early-2025 outflow regime; institutional
  bid is re-establishing.
- Fed pivot expectations rebuild liquidity tailwind (`WALCL` stabilising).

## Confirming evidence (current)

- BTC funding rates flat-to-negative — speculative excess flushed.
- MSTR/BTC ratio holding above its 52-week low — leveraged sentiment proxy
  not breaking down.
- USD weakening from Q1 2026 highs.

## Invalidating conditions

See frontmatter. Sequential lower-lows month-on-month kills the bottom thesis.
USD super-strength independently kills it (BTC and risk assets crushed under
those conditions).

## Trade implication

If `confirming`: enables Kronos to propose long entries on BTC + MSTR + IBIT.
If `violated`: auto-cancels the 24mo rally hypothesis with reason
"precondition_failed". Operator can manually resurrect once a fresh bottom-test
hypothesis is filed.

## Source / inspiration

Operator conviction; cycle-anchored timing draws on standard halving-cycle
heuristics + recent on-chain accumulation pattern reads.
