---
# Drop-in template — copy this to `.claude/hypotheses/draft/<slug>.md`, fill in,
# and we'll ingest it into the `hypothesis` table when M-2 ships.
name: ""
expected_dir: ""           # 'long' | 'short' | 'spread' | 'regime_shift'
ttl_months: 12
ratios:                    # symbols / FRED series this thesis predicts
  - ""
invalidators:              # plain-English conditions; will harden into DSL in M-2
  - ""
source_url: ""
created_at: 2026-04-30
---

# {{ name }}

## Thesis (1-2 paragraphs)

What's the claim, and over what horizon? Be specific enough that you'd recognise
it being wrong.

## Why now

What changed recently — or what didn't change despite expectation — that motivates
this hypothesis right now? If "always true" go re-read.

## Confirming evidence (current)

- Ratio / data point — value — interpretation.
- ...

## Invalidating conditions

- Specific, observable. Each should answer: *"if I saw this, I'd flip status to violated."*
- ...

## Trade implication

If `confirming`: which Kronos opportunities does this favor? (e.g. long energy,
short consumer discretionary, neutral on tech.) Goal is for the dashboard to
auto-tag opportunities once this hypothesis is `active`.

## Source / inspiration

Who said it, where, when. Public link. We don't ingest the source automatically
— this lets us cite later.
