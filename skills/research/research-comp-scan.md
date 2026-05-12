---
slug: research-comp-scan
title: Peer-set comparison scan
description: |
  Given a target ticker, identify a 4-7 name peer set from the operator's
  watchlist + The Street snapshots and produce a one-paragraph comparison
  on multiples, recent insider/political flow, and smart-money positioning.
  Verdict-only — no tool call. Use when the operator asks "how does X
  compare to its peers right now".
default: false
---

## Methodology

You are running a fast peer-set comparison for one operator's trading
decisions. The operator already has the target ticker on watchlist and
wants to know whether it sticks out vs the natural peer set on
positioning, valuation cluster, and recent flow.

Context:
- The bundle's EVIDENCE section may include vault chunks mentioning the
  target's name or sector. Use them to identify peers if no peer list is
  given in the query.
- The Street snapshot data (when present in the bundle as evidence chunks)
  tells you who's been buying — billionaires, trailblazers, insiders,
  politicians, options-bullish.
- Macro state is for regime context, not for direct comparison.
- Do NOT look up live prices or trading multiples — the bundle has what
  it has. If you can't ground a claim in the bundle, say so.

Your job per query:
1. Identify the target ticker and the peer set (4-7 names).
2. Note any peer where smart-money flow is *materially different* from
   the target — e.g. all peers have politician buys but the target
   doesn't, or a single trailblazer fund holds the target but every peer.
3. Produce a single paragraph (4-8 sentences) that names the peer set
   explicitly, calls out the most useful contrast, and ends with a
   one-sentence read on whether the target stands out positively,
   negatively, or sits with the cluster.

Hard rules:
- DO NOT propose a hypothesis or invalidator change. This skill is
  verdict-only.
- DO NOT recommend a buy/sell. The output is a comparison, not advice.
- NEVER invent peer names. If the bundle doesn't contain enough info to
  build a 4-name peer set, say so explicitly and stop.
- Cite the vault path of any concrete claim (e.g. "per
  The Street/snapshots/2026-05-08/tier-1-conviction.md, three
  billionaires added META").
- Be concrete with names + counts.

## Example query

How does META compare to its Big-Tech peers right now on positioning?

## Example verdict

Target: META. Natural peer set from the bundle: GOOGL, MSFT, AAPL, AMZN,
NVDA. The 2026-05-08 Street snapshot shows META with 4-channel cross-
conviction (3 billionaires, 7 trailblazer funds, 1 politician, 2 bullish
options sweeps) — the highest cross-channel breadth in the peer set.
GOOGL is also Tier 1 but lighter on signals (7 mentions vs META's 13).
MSFT and AMZN are Tier-2 / Tier-3 cluster names with heavy Trailblazer
crowding but no political or insider activity. AAPL is Tier-2 with
billionaire (Gayner) + 3 trailblazers + bullish options but no political
disclosure, distinguishing it as a quality-cluster pick rather than a
catalyst-driven one. **META stands out as the highest-conviction
positioning name in the peer set this snapshot, with the only crossover
between political disclosure and bullish options flow.** No
counter-positioning evidence in the bundle that would invert this read.
