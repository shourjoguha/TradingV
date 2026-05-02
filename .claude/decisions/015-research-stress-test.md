# ADR-015: Research stress-test endpoint — Phase 3

**Date**: 2026-05-02
**Status**: Accepted (Phase 3 shipped)

## Context

After Phase 1 (M-2 hypothesis object) and Phase 2 (vault + indexer)
shipped, the platform finally had a structured belief layer + an evidence
layer. The remaining wedge was a reasoning layer that wired both together
into something the operator couldn't get from a generic LLM chat.

Brainstorm 2026-05-02 converged on **stress-test as the primary use case**.
The original plan from 2026-05-01 sketched a kitchen-sink endpoint with
four action kinds + a frontend page; that plan was over-scoped before we
had real artifacts to plug into. ADR captures the locked v1 shape.

## Decisions

### 1. One use case for v1: stress-test the operator's own theses

Rejected: synthesis ("summarize this week's commentary"), advisory mode
("what should I trade?"), retrieval-only ("find me everything Lyn Alden
said about liquidity").

Accepted: read one hypothesis, read its linked evidence + live macro
state, return a verdict, propose ONE concrete invalidator DSL change.

**Reason:** stress-test produces an *actionable artifact* (an invalidator
update) that exercises the whole stack — hypothesis + vault + macro +
Claude — in a single query. Synthesis is easier to add later as a
second mode; the harder shape is the one that flows back into a row
mutation. Build the harder shape first; the easier modes fall out.

### 2. One action kind: `propose_invalidator_update`

Rejected v0 plan's four kinds: `update_invalidator`,
`cancel_hypothesis`, `create_opportunity`, `no_action`.

Accepted: just `propose_invalidator_update`. `no_action` collapses into
"don't call the tool." `cancel_hypothesis` is 30 seconds via the cancel
route — LLM proposing it adds approval-flow surface for negligible
saving. `create_opportunity` is M-3 territory and shipping it inside
Phase 3 means the LLM is making trade-shaped suggestions, which is a
much bigger blast radius for a small marginal value.

**Reason:** get the muscle memory right on one action shape. Expand
when 20+ stress-tests have shown what the operator actually wants from
the loop. Parked into roadmap as 8b.4.

### 3. Markdown answer in the vault, not a frontend page

Rejected: a `/research` page with cards + Approve/Dismiss buttons.

Accepted: each `/ask` writes a file at `<vault>/Research/<date>-<slug>.md`.
Operator opens it in Obsidian (already their preferred reader), ticks the
**Approve** checkbox, saves. The vault-indexer's `/promote` flow reads
the tick and HTTP-calls TradingView's `/v1/research/queries/{id}/approve`.

**Reason:** Phase 2 established that the operator's preferred ergonomic
is markdown checkboxes — `_review-queue.md` works that way already. A
new frontend page is build + maintain cost for *strictly worse* UX. The
Research/ files are also indexable for free, so retrieval over prior
stress-tests works without extra wiring.

### 4. Three-layer DSL validation gate

Server-side rejects Claude's tool call when:
1. `inv_dsl.validate_spec(proposed_invalidator)` fails (DSL malformed)
2. `hypothesis_slug` not in the bundle (Claude can't propose for theses
   it didn't see)
3. Any `evidence_paths` not in the bundle's evidence list (no citing
   hallucinated paths)

Failures drop the action; the markdown gets a verdict-only "no concrete
change" answer. Approve route re-validates DSL before patching the
hypothesis row (defense in depth — frontmatter could have been edited).

**Reason:** hallucinated DSL is the highest-leverage failure mode. The
LLM is otherwise hard to constrain; structured validation at the
boundary is the cheap reliable fix.

### 5. Anthropic SDK with prompt caching; no daily token budget

Cache the system prompt + bundle prefix via `cache_control: {type:
"ephemeral"}`. Repeat queries on the same hypothesis pay the cache-read
rate on the prefix.

No daily token budget. Surface `tokens_in`, `tokens_out`,
`est_cost_usd` per response.

**Reason:** at solo-operator volume, daily cost will be cents. Adding a
budget guard is overhead for a problem that won't materialize. If usage
genuinely scales, the per-response cost data is the trigger to add a
budget — and adding it later is a 15-minute change.

### 6. Weekly auto-stress per active hypothesis

A background loop (`app/research/weekly.py`) fires `/ask` once per active
hypothesis per week. Default counterargument-style query. Appends
one-line verdict summaries to `_review-queue.md` so unread answers
surface in the operator's tick-discipline pass.

**Reason:** the riskiest assumption flagged in the brainstorm was
"operator asks once and never goes back to read the answer file."
Periodic auto-stress is the cheapest hedge. If even the weekly summary
in the review queue goes unread for 2-3 weeks, the next move is a
Telegram digest (parked as roadmap 8b.5).

### 7. Vault-indexer is now aware of TradingView

The indexer's `/promote` was vault-only in Phase 2. Phase 3 adds
`research_hook.py` which scans `Research/*.md` for ticked Approve/Dismiss
boxes and HTTP-calls `TRADINGVIEW_API_URL/v1/research/queries/{id}/...`
using `TRADINGVIEW_API_KEY`.

**Reason:** the alternative (TradingView polls the vault for pending
ticks) requires more state and more moving parts. One env-driven HTTP
boundary is the minimum coupling; easy to swap.

### 8. Idempotency via banner stamping

After firing approve/dismiss, the indexer appends `<!-- vault-indexer:applied -->`
to the markdown. Subsequent `/promote` passes detect the banner and skip
the file. Idempotent re-approves on the TradingView side return
`already_approved` without re-patching.

**Reason:** prevents double-apply on indexer restarts or redundant
`/promote` calls. Operator can also hand-edit the banner away if they
genuinely want to re-fire (rare but supported).

## Consequences

- ~1300 lines new code (app/research/* + tools/vault_indexer/research_hook.py).
- 13 new tests; full suite 341 green.
- Migration 0023 adds `research_queries` audit table.
- Lifespan wires the research-weekly task. Off-key path is
  cheap-to-keep — when `ANTHROPIC_API_KEY` is missing the inner loop
  logs + skips.
- The vault-indexer carries one TradingView coupling. Easy to swap
  later (e.g. when the indexer extracts to its own repo).
- The `Research/` folder will accumulate over time. Each file is ~1 KB
  of markdown plus the banner. Acceptable; eventually a "clean up
  applied research files older than 6 months" backlog item will appear.

## Alternatives considered

- **Multiple action kinds** in v1: rejected — start tiny, expand later.
- **Frontend research page**: rejected — operator's tick-in-Obsidian
  ergonomic is already proven.
- **Daily token budget**: rejected as premature.
- **Streaming responses**: rejected — solo operator, no UI urgency.
  Parked as 8b.8.
- **Multi-LLM cross-check** (Claude + GPT): rejected for v1 — adds API
  cost + complexity. Parked as 8b.7; revisit only if proposals
  disagree with operator gut > 30%.
- **Pure pull model** (TradingView polls the vault): rejected — adds
  state + latency. Push via indexer HTTP is simpler.

## Footer — UI surface decision (2026-05-02)

After Phase 3 backend shipped, brainstorm covered three shapes for
the UI:

1. Single-turn thin shell (`/research` page) — chosen as Phase 3.7
   ([plan](../plans/phase-3.7-research-ui-single-turn.md)).
2. Multi-turn threading — direction-only at Phase 3.8
   ([sketch](../plans/phase-3.8-research-ui-threading.md)). Gated on
   operator hitting "asked the same hypothesis 3+ times in a week and
   wished the answers knew about each other."
3. Free-form open chat over the corpus — **OUT OF SCOPE**. Operator
   uses the Claude API directly when they want open-ended discussion.
   Claude can read this stack as context AND perform outside research;
   building a generic chat UI inside TradingView would duplicate that
   without differentiation. Captured at roadmap 8b.10 with the
   explicit out-of-scope marker.

Markdown answer files in `<vault>/Research/` keep getting written
regardless of UI surface. The Phase 3.7 page is a *complementary*
surface for in-context approve/dismiss; the file artifact is still
the archival record + the weekly-auto-stress target. Two surfaces is
acceptable here because they share one backend and one approval
flow — no second source of truth.
