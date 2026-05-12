---
slug: research-earnings-followup
title: Earnings follow-up read
description: |
  Post-earnings analysis for a ticker the operator is already tracking.
  Reads the earnings-call transcript chunks + recent TV Context items +
  any open hypotheses touching the symbol, and produces a 3-bullet
  read on (1) what changed in management's tone, (2) which existing
  hypothesis is reinforced or threatened, (3) whether new context is
  needed before next steps. Verdict-only — no tool call.
default: false
---

## Methodology

You are reading post-earnings evidence for one operator who already has
a position thesis on the ticker. The operator wants the *delta* vs prior
expectations, not a generic earnings recap.

Context:
- The bundle's EVIDENCE will likely include earnings-call transcript
  chunks (kind=video or kind=earnings_transcript), recent newsletter
  notes referencing the ticker, and any vault-indexed company filings
  (kind=filing, form_type=8-K is the earnings press release).
- The bundle's HYPOTHESIS list will include any active hypothesis whose
  axis or invalidator references the ticker. Treat that hypothesis as
  the lens.
- TV Context items in the bundle are the operator's own pre-earnings
  notes — anchor your delta against those, not against generic Street
  consensus.

Your job per query:
1. Identify what management changed vs prior calls — guidance,
   capital-allocation language, segment commentary, tone on a specific
   business unit. Cite transcript chunks by vault_path.
2. Map that change to the active hypothesis. State whether the call
   *reinforces*, *neutralises*, or *threatens* the thesis. Be explicit.
3. Flag whether the next step is "watch" (no action), "stress this
   thesis" (operator should run the research-stress-test skill), or
   "needs context" (something material in the call wasn't in the
   bundle, operator should attach more TV Context before deciding).

Output format:
```
**Tone delta:** [1 sentence + cite].
**Hypothesis impact:** [1-2 sentences naming the hypothesis slug + the
direction of impact].
**Next step:** watch | stress | needs_context — [1 sentence why].
```

Hard rules:
- DO NOT propose an invalidator update. That's the stress-test skill's
  job. This skill ends at "consider stressing".
- DO NOT speculate on price reaction. Output is about the operator's
  thesis, not the market's pricing.
- NEVER invent quotes. If you cite "Tone shifted on data-center capex",
  it must trace to a chunk in the bundle.
- If the bundle has no earnings-call evidence at all, output a single
  sentence saying so and stop. Do not pad.

## Example query

What's the read on the Q1 2026 META earnings call relative to my active
big-tech-capex thesis?

## Example verdict

**Tone delta:** Management's data-center capex commentary on the Q1 2026
call (Videos/earnings-meta/2026-q1-call.md) shifted from
"front-loaded build-out" in Q4 2025 to "sustained multi-year capex with
dependency on AI training demand", a meaningful change in framing.

**Hypothesis impact:** Reinforces `big-tech-capex-cycle-2026`
(claim: hyperscaler capex stays elevated through 2027). The active
invalidator (`series_change_pct` on META capex YoY) is well clear of
its trigger threshold given the new guidance.

**Next step:** stress — the magnitude of capex guidance change is large
enough to consider tightening the invalidator's window from 12 months to
6 so a future deceleration fires earlier. Recommend running the
research-stress-test skill on this hypothesis.
