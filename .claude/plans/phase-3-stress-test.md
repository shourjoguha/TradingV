# Phase 3 — Stress-test endpoint

> Brainstorm 2026-05-02 converged on **stress-test as the primary use case** for v1. Synthesis (`/research/digest`), additional action kinds (`cancel_hypothesis`, `create_opportunity`), Telegram digests, cross-hypothesis stress, multi-LLM cross-check, and streaming + frontend page are all parked in the active [roadmap](../roadmap.md) as 8b.3–8b.8.

## Context

Phase 1 (M-2) shipped the structured belief layer. Phase 2 shipped the
evidence substrate (vault + indexer). Phase 3 wires both into a Claude
reasoning layer that **stress-tests one hypothesis at a time** and
proposes ONE concrete DSL change against the existing API surface.

Core value loop:

```
operator query
  → bundle hypothesis + evidence + macro + accuracy
  → Claude Sonnet with one-shot example + tool-use schema
  → answer written to ~/Documents/knowledge-vault/Research/<date>-<slug>.md
  → operator reads in Obsidian
  → ticks "Approve" checkbox if the proposed DSL change makes sense
  → vault-indexer's promote loop calls PATCH /v1/hypotheses/{id}
  → next nightly tick re-evaluates with the new threshold
```

**Zero new frontend code.** Obsidian renders the answers; the same
checkbox-promote contract from Phase 2 handles approvals.

## Locked decisions

1. **Single endpoint** — `POST /v1/research/ask`. No `/digest`, no
   `/synthesize` for v1.
2. **One action kind** — `propose_invalidator_update`. Defer
   cancel/create-opportunity until 20+ stress-tests run.
3. **Markdown answer in the vault** — folder `Research/`. Each answer
   file is itself indexable, so retrieval over prior stress-tests works
   for free ("what did I stress-test about BTC last quarter?").
4. **Indexer applies ticks** — same promote contract as
   `_review-queue.md`. The indexer needs HTTP knowledge of TradingView
   to fire `PATCH /v1/hypotheses/{id}`.
5. **Server-side DSL validation** — Claude's `proposed_invalidator`
   passes `app.hypotheses.invalidator.validate_spec()` BEFORE the
   markdown is written. Hallucinated DSL never reaches the operator.
6. **No daily token budget** — surface `tokens_in`, `tokens_out`,
   `est_cost_usd` per query. If usage genuinely scales, the data tells
   us to add a budget. Premature today.
7. **Weekly auto-stress routine** — fires once per active hypothesis
   from the lifespan tick, drops a one-line summary into
   `_review-queue.md` so unread answers get noticed.
8. **Anthropic SDK + prompt caching** — bundle is mostly stable across
   queries for the same hypothesis; cache the system prompt + the
   bundle prefix to halve cost per repeat.

## Schema — `migrations/versions/0023_research_queries.py`

```sql
CREATE TABLE research_queries (
  id UUID PRIMARY KEY,
  asked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  query TEXT NOT NULL,
  hypothesis_ids JSONB NOT NULL DEFAULT '[]',  -- list of slugs (or row ids)
  answer_path TEXT,                            -- vault-relative; nullable on error
  verdict TEXT,                                -- one-line verdict for log scan
  tokens_in INT,
  tokens_out INT,
  est_cost_usd NUMERIC(10, 6),
  -- Raw payloads kept for replay / forensics. Trim later if it bloats.
  bundle JSONB,
  response JSONB,
  -- Status tracks operator follow-through.
  status TEXT NOT NULL DEFAULT 'pending'       -- pending | approved | dismissed
    CHECK (status IN ('pending', 'approved', 'dismissed', 'error')),
  approved_at TIMESTAMPTZ,
  approved_action JSONB                        -- the DSL that actually got applied
);

CREATE INDEX research_queries_asked_at ON research_queries (asked_at DESC);
```

JSON not JSONB so SQLite test parity stays free.

## Module layout — `app/research/`

```
app/research/
  __init__.py
  models.py        ResearchQuery ORM model
  schemas.py       Pydantic: AskRequest, AskResponse, ResearchQueryRead
  bundle.py        Assemble the LLM input (hypotheses, evidence, macro, accuracy)
  prompts.py       SYSTEM_PROMPT, ONE_SHOT_EXAMPLE, render_user_message()
  client.py        Anthropic SDK wrapper with prompt caching + cost calc
  service.py       Orchestrates: bundle → call → validate DSL → render md → persist
  routes.py        POST /v1/research/ask, GET /v1/research/queries[/{id}]
  rendering.py     Render the answer markdown template
  weekly.py        Weekly auto-stress task (lifespan-spawned)
```

### `bundle.py` — the LLM input

```python
def build_bundle(query: str, *, hypothesis_slugs: list[str] | None = None) -> dict:
    """Returns:
    {
      "query": str,
      "hypotheses": [HypothesisCard, ...],   # default: all status=active
      "macro_state": {...},
      "evidence": [ExcerptCard, ...],        # decay-weighted from vault-indexer
      "accuracy_snapshot": {...},
    }"""
```

**HypothesisCard:**
```python
{
  "slug", "title", "claim_type", "axis",
  "primary_metric", "tracking_signal",
  "invalidator": {...},                # full DSL
  "status", "expires_at",
  "recent_evaluations": [...],         # last 3
  "linked_vault_paths": [...],         # from hypothesis_node_links
}
```

**ExcerptCard:**
```python
{
  "vault_path", "title", "kind",
  "section", "text",                   # truncated to 800 chars
  "published_at", "author",
  "similarity", "decay_weight", "score",
}
```

Retrieval via vault-indexer HTTP `GET /search?q=...&k=12`. If
hypothesis has `linked_vault_paths` set in `hypothesis_node_links`, prefer
those. Otherwise generic search on `query`.

**Macro snapshot:** for each hypothesis, fetch current value of
`tracking_signal` and any symbols inside `invalidator.args` from
`app.macro.service.compute_ratio()` or `MacroSeries` direct.

**Accuracy snapshot:** for any tickers mentioned in the bundle, last 14d
hit-rate + MAPE from `app.accuracy.service`.

**Hard truncation** to ~8k tokens of bundle. If over: drop oldest
evaluations first, then trim excerpts by score.

### `prompts.py` — system prompt + one-shot

System prompt frames the operator-as-system-operator (not retail user),
the action as a *suggestion for human review*, and stresses
factual-grounding-in-bundle.

One-shot example shows a stress-test verdict + a `propose_invalidator_update`
tool call against a synthetic thesis. Anchor for output shape; ~300
tokens. Prevents hedging.

### `client.py` — Anthropic SDK call

```python
async def ask_claude(*, system: str, bundle_text: str, query: str, tools: list) -> ClaudeResponse:
    """Single call. Uses Anthropic SDK with:
      - prompt cache marker on the system + bundle prefix
      - tool_choice=auto so Claude can return either a text-only verdict
        OR a verdict + propose_invalidator_update tool call
      - max_tokens=2000
      - temperature=0.3 (focused, not creative)
    Returns parsed verdict + tool calls + token usage.
    """
```

Cost calc reads from response usage. Anthropic pricing in env:
`CLAUDE_INPUT_COST_PER_MTOK`, `CLAUDE_OUTPUT_COST_PER_MTOK`,
`CLAUDE_CACHE_READ_COST_PER_MTOK`.

### Tool-use schema

```python
TOOL_PROPOSE_INVALIDATOR = {
    "name": "propose_invalidator_update",
    "description": (
        "Propose tightening or loosening one hypothesis's invalidator DSL. "
        "The operator reviews + approves before any change is applied. "
        "ONLY call this when the bundle's evidence supports a concrete change. "
        "Use ONLY the operator's existing 5-op DSL: ratio_below_sma, "
        "series_above_threshold, series_below_threshold, series_change_pct, manual."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hypothesis_slug": {"type": "string"},
            "rationale": {"type": "string"},
            "proposed_invalidator": {
                "type": "object",
                "properties": {
                    "op": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["op", "args"],
            },
            "evidence_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Vault paths supporting the proposal.",
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["hypothesis_slug", "rationale", "proposed_invalidator", "confidence"],
    },
}
```

Server-side after Claude returns:
1. `inv_dsl.validate_spec(proposed_invalidator)` — reject on raise.
2. Verify `hypothesis_slug` exists in the bundle (Claude can't propose
   for a hypothesis it didn't see).
3. Verify `evidence_paths` are all in the bundle's `evidence` list
   (Claude can't reference a path it didn't see).

Failures drop the proposed action and write a verdict-only answer file.

### Markdown answer template

`tools/vault_indexer/`-aware path: `<vault>/Research/<date>-<slug>.md`.

```markdown
---
kind: research_answer
title: "Stress-test: btc-bottom-3m"
hypothesis_slug: btc-bottom-3m
asked_at: 2026-05-02T18:00:00Z
research_query_id: <uuid>
tags: [research]
---

# Stress-test: btc-bottom-3m — 2026-05-02

**Query:** what's at risk in my BTC bottom thesis?

**Verdict:** Thesis still tenable but the DXY invalidator threshold of 110 is on
the edge. Two pieces of evidence point to USD strength persisting past
the stated 30-day window.

## Evidence

- [[Newsletters/lyn-alden/2026-w19.md]] — flags structural USD bid through Q3 (score 0.78)
- [[Books/lyn-alden-broken-money/dollar-regimes.md]] — chapter 4 on dollar
  regimes (score 0.52)
- Macro: DXY currently 109.4, 5-day average 108.9 (below 110, trending up)

## Proposed action

- [ ] **Approve:** tighten `btc-bottom-3m` invalidator threshold from 110 → 108
  - Op: `series_above_threshold`
  - Args: `{symbol: DX-Y.NYB, threshold: 108, days_above: 30}`
  - Rationale: 110 only fires on a sustained breakout; current evidence
    suggests 108 is the actionable signal level for this thesis.
  - Confidence: 0.7

To dismiss, simply leave the box unticked. Ticking the approve box
will trigger `PATCH /v1/hypotheses/btc-bottom-3m` on the next indexer
watch event.

---

*tokens_in: 4123 · tokens_out: 891 · est_cost_usd: $0.018*
```

The frontmatter `kind: research_answer` lets the vault-indexer detect
the file kind without parsing body. The `tags: [research]` provides a
default tag so operator can filter for them.

### Service flow — `service.py`

```python
async def ask(query: str, hypothesis_slugs: list[str] | None) -> AskResponse:
    bundle = await build_bundle(query, hypothesis_slugs=hypothesis_slugs)
    bundle_text = render_bundle_text(bundle)         # deterministic prompt-cacheable
    response = await ask_claude(
        system=SYSTEM_PROMPT,
        bundle_text=bundle_text,
        query=query,
        tools=[TOOL_PROPOSE_INVALIDATOR],
    )
    proposed = _validate_proposed_action(response, bundle)  # may be None
    answer_path, body = _render_markdown(query, bundle, response, proposed)
    _write_to_vault(answer_path, body)
    qid = await _persist_query(...)
    return AskResponse(answer_path=answer_path, query_id=qid, ...)
```

### Routes

```
POST /v1/research/ask              { query, hypothesis_slugs?: [...] }
GET  /v1/research/queries          list (paginated)
GET  /v1/research/queries/{id}     detail with bundle + response
POST /v1/research/queries/{id}/approve   {}  — apply proposed_action
POST /v1/research/queries/{id}/dismiss   {}  — mark dismissed
```

The approve/dismiss routes are what the vault-indexer calls when it
reads a tick. A small middleware: `approve` re-validates the DSL before
patching the hypothesis (defense in depth — frontmatter could have been
edited).

### Vault-indexer Research-folder hook

Indexer's `review.promote()` already handles `_review-queue.md`. We
need a parallel handler for `Research/<date>-<slug>.md` files when
their checkbox is ticked.

New module `tools/vault_indexer/research_hook.py`:

```python
def scan_research_ticks(vault_root: Path) -> list[dict]:
    """Walk Research/*.md, find ticked checkboxes that reference an action,
    return list of {research_query_id, action: 'approve'|'dismiss'}.

    Uses the frontmatter's `research_query_id` to tie back to the
    server-side row."""
```

Wired into `app.py` `POST /promote` flow: parse `_review-queue.md`
ticks (existing) AND scan `Research/` ticks. For each Research tick,
HTTP-call TradingView's `POST /v1/research/queries/{id}/approve`.

Indexer needs `TRADINGVIEW_API_URL` + `TRADINGVIEW_API_KEY` env vars.

### Weekly auto-stress

`app/research/weekly.py`:

```python
async def weekly_loop(stop_event):
    """Once per week, for each hypothesis with status='active':
       1. ask({query: "What's the strongest counterargument or risk to this
          thesis based on recent vault content + current macro state?",
          hypothesis_slugs: [slug]})
       2. Append a one-line summary into _review-queue.md so the operator
          notices on their next review pass."""
```

Spawned from `app/main.py` lifespan, similar to the existing accuracy /
drift loops. Sleep interval = 7 days; first tick deferred 1 hour after
boot.

## Effort

| Step | Effort |
|---|---|
| Migration 0023 + ResearchQuery model | 30 min |
| `bundle.py` (hypothesis card + macro + accuracy + indexer search) | 2 hrs |
| `prompts.py` (system + one-shot example + bundle template) | 1 hr |
| `client.py` (Anthropic SDK + caching + cost calc) | 30 min |
| `rendering.py` (markdown template) | 30 min |
| `service.py` (orchestrate + validate + persist) | 1 hr |
| `routes.py` (ask + queries + approve/dismiss) | 30 min |
| `weekly.py` + lifespan wiring | 1 hr |
| Indexer Research-tick hook + HTTP-to-TradingView | 1 hr |
| Tests (~12) | 2 hrs |
| **Total** | **~10 hrs** |

## Tests

- `bundle.py` synthesizes correct shape from synthetic hypothesis +
  vault rows + macro series.
- DSL validation rejects hallucinated specs (unknown op, malformed args).
- Markdown render: hypothesis with proposed action vs without.
- Route round-trip: `ask` → file in vault, row in DB.
- Approve route: validates DSL again, patches hypothesis, marks query
  approved.
- Dismiss route: marks query dismissed, no patch.
- Weekly loop: fires per active hypothesis, writes one-liner to
  `_review-queue.md`.
- Indexer tick scanner: parses Research/*.md ticks correctly.
- Cost calc: tokens × pricing → expected USD.
- One-shot example in prompt is well-formed JSON.
- Bundle truncation: oversized bundle drops oldest evaluations first.
- DSL hallucination: Claude returns invalid op → no answer file action
  block, verdict-only.

## Verification (UAT)

1. `alembic upgrade head` clean.
2. Full suite green (current 328 + 12 new = 340).
3. `POST /v1/research/ask` against `btc-bottom-3m` with the canonical
   query → markdown file lands at `Research/<date>-btc-bottom-3m.md`,
   evidence chunks include vault excerpts (decay-weighted), proposed
   action references the operator's actual DSL, est_cost_usd > 0.
4. Tick the approve box, save → indexer's `POST /promote` fires →
   TradingView `POST /v1/research/queries/{id}/approve` → DSL applied
   → next nightly hypothesis tick re-evaluates with new threshold.
5. Weekly loop manually invoked → 6 active hypotheses → 6 markdown
   files in `Research/` + 6 lines in `_review-queue.md`.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Claude hedges, no tool call | M | One-shot example + system prompt framing. If still hedges, lower temperature, raise stakes in prompt language. |
| Hallucinated DSL | L | Server-side `validate_spec` BEFORE writing markdown; second validation on approve. |
| Operator forgets to read answer files | M | Weekly auto-stress + summary in `_review-queue.md`. If still unread, Phase 3.3 Telegram digest. |
| Indexer ↔ TradingView coupling | L | Indexer becomes aware of one HTTP endpoint. Easy to swap (env-driven). |
| Bundle bloat / token cost | L | Hard 8k-token cap; truncation policy spelled out; cost surfaced per response. |
| Prompt-cache invalidation | L | Bundle prefix is deterministic-stable; cache key is the hash. If miss-rate is high, profile and fix. |

## Out of scope (parked into roadmap, see 8b.3–8b.8)

- Synthesis mode (`/research/digest`)
- Action kinds: `cancel_hypothesis`, `create_opportunity`
- Telegram digest of unread answers
- Cross-hypothesis stress (one query, multiple theses)
- Multi-LLM cross-check (Claude + GPT)
- Streaming responses + frontend research-history page
