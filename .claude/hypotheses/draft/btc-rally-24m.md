---
name: "BTC + MSTR sharp climb over 24 months"
slug: "btc-rally-24m"
parent_id: null
precondition_id: "btc-bottom-3m"         # NEW SEMANTIC: existence-dependency
                                         # If precondition becomes 'violated', this
                                         # auto-cancels with reason 'precondition_failed'.
expected_dir: "long"
claim_type: "absolute"
primary_metric: "basket:BTC-USD+MSTR"    # success = both materially up; thresholds in body
tracking_signal: "MSTR/BTC-USD"          # mNAV — leading indicator for both
ttl_months: 24
ratios:
  - "BTC-USD"
  - "MSTR"
  - "MSTR/BTC-USD"                       # mNAV proxy
  - "BTC-USD/GC=F"                       # BTC vs gold (debasement regime)
  - "WALCL"                              # Fed BS
  - "T10YIE"                             # inflation expectations
  - "DX-Y.NYB"
invalidators:
  # BTC fails to climb meaningfully
  - "BTC-USD < its bottom-print + 25% at month 12"
  - "BTC-USD makes a new low below the precondition's bottom price at any time"
  # Sector-regime breakdown
  - "BTC-USD/GC=F < 200-day SMA for 90 consecutive days"
  # MSTR-specific failure (kills MSTR leg only; BTC leg can survive)
  - "MSTR/BTC-USD < 1.0 sustained for 60 days (mNAV breakdown — equity issuance overhang or convertible-debt rollover stress)"
  # Macro tailwind reversal
  - "WALCL contracts > 8% from current level over a rolling 6-month window"
source_url: ""
created_at: 2026-04-30
---

# BTC + MSTR sharp climb over 24 months

## Thesis (1-2 paragraphs)

Conditional on a tradable bottom forming within 3 months
(see [`btc-bottom-3m.md`](btc-bottom-3m.md)), expect **BTC** and **MSTR** to
deliver a sharp climb over the following 24 months. The driver stack:

1. **Halving-cycle mechanics** — post-halving supply shock + lagged demand
   response historically delivers cycle peaks 12-18 months post-halving.
   Halving was April 2024 → peak window approximately mid-2025 → mid-2026,
   meaning the 24mo TTL captures the bulk of cycle upside.
2. **USD-debasement / liquidity expansion** — Fed pivot regime + global
   liquidity expansion bid hard-money assets. BTC is the cleanest proxy.
3. **MSTR convexity** — MSTR provides ~2-3x leveraged BTC exposure via
   the Saylor-led accumulation flywheel. When BTC climbs, mNAV expands;
   MSTR equity issuance becomes accretive again, reinforcing the cycle.

Success criterion: at TTL expiration, both BTC and MSTR materially higher
than the precondition's bottom price (≥ 100% for BTC; ≥ 200% for MSTR given
its leverage profile). Partial confirmation (only BTC delivers) is logged
but doesn't count as full success.

## Why two names, one hypothesis

| Name | Role | Primary failure mode |
|---|---|---|
| BTC-USD | The actual asset; cycle-driven | New cycle low; macro liquidity reversal |
| MSTR | Levered BTC proxy via balance sheet | mNAV collapse from over-issuance or convertible-debt rollover stress |

MSTR is **mechanically dependent on BTC** but has independent failure modes
that BTC doesn't share. The MSTR-specific invalidator (`MSTR/BTC-USD < 1.0`
sustained) catches "BTC up but MSTR broken." Encoding both lets the system
distinguish "thesis fully right" from "BTC right, MSTR-leverage-broken."

## Why now

Conditional on the precondition; same drivers apply. Standalone reasoning:

- Cycle window aligns: April 2024 halving → expected peak Q2-Q4 2026.
- Institutional flows post-ETF: persistent demand floor that didn't exist
  in prior cycles.
- Fed BS expansion or stable trajectory through 2026 = liquidity tailwind.

## Confirming evidence (current)

- BTC ETF cumulative inflows trending up.
- MSTR/BTC ratio holding above 1.0 (mNAV intact).
- BTC dominance rising (alt-coin rotation hasn't drained the bid).

## Invalidating conditions

See frontmatter. Five invalidators across three categories:

- **BTC-leg fails** — fails to deliver meaningful upside or makes a new low.
- **MSTR-leg fails** — mNAV breakdown; kills MSTR exposure but BTC may
  still play out.
- **Macro reversal** — Fed BS contracts hard, removing the liquidity
  underpinning.

## Trade implication

If `confirming`: structural overweight in BTC + MSTR + IBIT. Tilt Kronos
opportunities toward BTC-correlated names (mining majors, payments names with
BTC exposure) and away from "BTC-substitute" trades that compete for the same
narrative bid (gold majors held flat or underweight).

If MSTR leg violates but BTC leg holds: close MSTR position, hold BTC + IBIT.
If precondition fails: hypothesis auto-cancels; revisit only after a fresh
bottom-formation hypothesis files.

## Source / inspiration

Operator conviction. Cycle framing standard in halving-cycle literature
(PlanB / s2f, with all caveats). MSTR-as-leverage thesis aligns with Saylor's
public communications and Galaxy Digital research.
