---
id: macro_liquidity
title: Liquidity & Credit
default_axis: liquidity
panels:
  - kind: ratio
    numerator: WALCL
    denominator: GDP
    sma_days: 200
  - kind: series
    symbol: DGS10
    threshold: 4.5
  - kind: hypothesis_filter
    axis: liquidity
---

# Liquidity & Credit

Snapshot of the operator's liquidity-axis context: Fed BS / GDP ratio
versus its 200-day SMA, the 10-year yield watermark, and the active
hypotheses tagged ``axis: liquidity``.
