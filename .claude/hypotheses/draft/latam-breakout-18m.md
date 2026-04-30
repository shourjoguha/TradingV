---
name: "LatAm breakout — tactical confirmation (18mo)"
slug: "latam-breakout-18m"
parent_id: "latam-breakout-36m"    # child of the structural thesis
expected_dir: "long"
claim_type: "absolute_with_relative_signal"
primary_metric: "ILF"
tracking_signal: "ILF/SPY"
ttl_months: 18
ratios:
  - "ILF"
  - "ILF/SPY"
  - "EWZ"
  - "EWW"
  - "DX-Y.NYB"
invalidators:
  # Tighter than the structural parent — 18mo failure is meaningful evidence
  # but not fatal to the 36mo thesis.
  - "ILF/SPY < 200-day SMA for 30 consecutive trading days"
  - "EWZ closes below its multi-decade trendline (~$25) for 6 weeks"
  - "DX-Y.NYB > 110 sustained for 45 days"
source_url: ""
created_at: 2026-04-30
---

# LatAm breakout — tactical confirmation (18mo)

## Thesis (1-2 paragraphs)

The 18-month confirmation of the structural LatAm thesis (see
[`latam-breakout-36m.md`](latam-breakout-36m.md)). Over the next 18 months
expect `ILF` and `EWZ` to hold their breakouts above the multi-decade
resistance and `ILF/SPY` to make a new higher-high relative to its
2024-2025 base.

If the 18mo plays out: structural thesis is on track; sizing can scale.
If 18mo fails: **structural thesis is questioned but not dead** — multi-decade
breakouts can retrace 30-50% before continuing. The parent's invalidators are
deliberately wider.

## Why now

The first 18 months post-breakout are where most fakeouts get exposed. This
hypothesis exists to give the operator a tighter feedback loop than the 36mo
parent, so position sizing can react faster to invalidation without
prematurely killing the structural view.

## Confirming evidence (current)

- `EWZ` and `ILF` above their 50-day and 200-day SMAs simultaneously.
- `ILF/SPY` printing higher highs and higher lows since the breakout candle.
- Brazil real (`BRL`) and Mexican peso (`MXN`) holding firm against `USD`.

## Invalidating conditions

Tighter thresholds than the parent — see frontmatter. A failure here flips
status to `violated`, which downgrades sizing on LatAm trades but does **not**
auto-invalidate the parent.

## Trade implication

Drives **active sizing** for tactical Kronos opportunities in LatAm names.
When `confirming`, tilt Kronos opportunity ranking toward EM-LatAm tickers.
When `violated`, fall back to neutral sizing even if the 36mo parent is still
`active` — wait for re-confirmation before adding tactical exposure.

## Source / inspiration

Otavio Costa, Crescat — same source as parent.
