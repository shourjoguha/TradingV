---
name: "LatAm breakout — structural (36mo)"
slug: "latam-breakout-36m"
parent_id: null                    # this is the parent thesis
expected_dir: "long"
claim_type: "absolute_with_relative_signal"
primary_metric: "ILF"              # absolute return — what "true" means
tracking_signal: "ILF/SPY"         # early-warning — what you watch day-to-day
ttl_months: 36
ratios:
  - "ILF"                          # broad LatAm — primary
  - "ILF/SPY"                      # relative early-warning
  - "EWZ"                          # Brazil
  - "EWW"                          # Mexico
  - "DX-Y.NYB"                     # USD — inverse co-mover
  - "HG=F"                         # copper — commodity-cycle tailwind
invalidators:
  - "ILF/SPY < 200-day SMA for 60 consecutive trading days"
  - "EWZ closes below its multi-decade trendline (~$25) for 12 weeks"
  - "DX-Y.NYB > 115 sustained for 90 days"
  - "Copper (HG=F) breaks below a 5-year support — commodity-cycle thesis falls"
source_url: ""                     # paste Costa post/letter URL
created_at: 2026-04-30
---

# LatAm breakout — structural (36mo)

## Thesis (1-2 paragraphs)

LatAm equities (Brazil + Mexico-led) have broken out of a multi-decade
downtrend. Over a 3-year horizon I expect **absolute** outperformance driven
by three structural tailwinds:

1. **Commodity supercycle revival** — copper / industrial metals demand from
   energy-transition build-out + Chinese stimulus + chronic underinvestment in
   mining capex during the 2014-2020 bear.
2. **Non-US trade integration** — Brazil and Mexico deepening trade ties with
   China and BRICS+; nearshoring to Mexico from US-China decoupling. Both
   reduce dependence on US-led capital flows.
3. **USD-debasement / multipolar regime** — end of the multi-decade
   USD-strength regime; capital rotates from US-overweight portfolios into
   hard-asset-exposed economies.

The claim is absolute (LatAm absolute returns positive over 36mo); the
**day-to-day tracking signal is relative** (`ILF/SPY`) because relative
breakdowns lead absolute ones.

## Why now

ILF and EWZ both crossed long-term resistance after a 14-year base. Costa's
framing — end of multi-decade USD-strength regime — implies a structural
rotation, not a tactical bounce. Confluence with the China-stimulus cycle
and Mexico-nearshoring story is the strongest setup in a decade.

## Confirming evidence (current)

- `ILF/SPY` trending above its 200-day SMA.
- `EWZ` holding above the broken multi-decade trendline.
- LatAm–China trade volumes growing YoY.
- Mexico FDI flows hitting multi-year highs (nearshoring).

## Invalidating conditions

See frontmatter. Any one of the four flips status to `violated`. The first two
are technical (price-action killing the breakout); the second two are
macro-structural (the underlying thesis no longer holds).

## Trade implication

If `confirming`: tilt Kronos opportunities toward LatAm-listed names and
EM-tagged tickers in the watchlist. Penalize opportunities reliant on
USD-strength regimes (e.g. heavily import-dependent LatAm consumer staples
that get crushed when local currencies firm).

Size structural overweight only when this thesis is `confirming`. Tactical
sizing is governed by the 18mo child hypothesis (`latam-breakout-18m.md`).

## Source / inspiration

Otavio Costa, Crescat — pin the specific post/letter URL above when you next
review. Reinforced by Stanley Druckenmiller's USD-debasement framing.
