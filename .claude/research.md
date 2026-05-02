# Research — stress-test endpoint

Phase 3 of the macro-workbench → decision-tool roadmap (shipped
2026-05-02). The unique-wedge layer: Claude reads the operator's
structured beliefs (Phase 1 hypotheses) + curated evidence (Phase 2
vault) + live macro state, returns a verdict, and proposes ONE concrete
DSL change against the operator's existing API surface. Operator
approves via a markdown checkbox in Obsidian — zero new frontend.

## Endpoints

```
POST /v1/research/ask                       { query, hypothesis_slugs?: [...] }
GET  /v1/research/queries[?status=]         paginated history
GET  /v1/research/queries/{id}              detail incl. bundle + raw response
POST /v1/research/queries/{id}/approve      apply the proposed action
POST /v1/research/queries/{id}/dismiss      mark dismissed (no-op on hypothesis)
```

`/ask` returns:
```json
{
  "query_id": "uuid",
  "answer_path": "Research/2026-05-02-btc-bottom-3m.md",
  "verdict": "Thesis weakening — DXY trending up.",
  "tokens_in": 4123,
  "tokens_out": 891,
  "est_cost_usd": 0.018,
  "proposed_action": {...} | null,
  "status": "pending"
}
```

The answer body lives in the markdown file at `<vault>/{answer_path}`.
The operator opens it in Obsidian. Ticking the **Approve** checkbox →
indexer's `/promote` flow → TradingView `/v1/research/queries/{id}/approve`
→ hypothesis row's `invalidator` is patched.

## Bundle composition

For each requested hypothesis (or every active row when
`hypothesis_slugs` omitted):

- Hypothesis card: slug, title, claim_type, axis, status, expires_at,
  primary_metric, tracking_signal, current `invalidator` JSON, last 3
  `hypothesis_evaluation` rows, linked vault paths via
  `hypothesis_node_links`.
- Evidence: top-K vault excerpts from the vault-indexer
  (`GET :8001/search?q=&k=`). When `linked_vault_paths` exists, prefer
  those; fall back to generic search if the linked-only filter starves
  the result set.
- Macro snapshot: latest value for each `tracking_signal` plus any
  symbol named in `invalidator.args`.
- Accuracy snapshot: 14-day hit-rate + MAPE for tickers mentioned in
  the bundle (best-effort; missing module is a no-op).

Hard token cap (default 8k). Truncation order: oldest evaluations →
lowest-score excerpts → trim longest excerpt body.

## Tool-use schema

Single tool: `propose_invalidator_update`. Forces structured JSON output
that maps directly onto the existing 5-op DSL
(`ratio_below_sma`, `series_above_threshold`, `series_below_threshold`,
`series_change_pct`, `manual`).

Server-side validates BEFORE writing the markdown:
1. `inv_dsl.validate_spec(proposed_invalidator)` — DSL well-formed
2. `hypothesis_slug` must appear in the bundle (no proposing for
   theses Claude wasn't shown)
3. `evidence_paths` must all appear in the bundle's evidence list (no
   citing hallucinated content)

Failures drop the action; the markdown gets a verdict-only "no concrete
change" answer instead.

## Markdown answer template

Frontmatter:
```yaml
---
kind: research_answer
title: "Stress-test: <slug>"
hypothesis_slug: <slug>
asked_at: <iso>
research_query_id: <uuid>
tags: [research]
---
```

Body sections: Query → Verdict → Evidence (wikilinks + decay-weighted
score) → Macro state → Proposed action (one Approve checkbox) →
Cost line.

## Approval flow

Operator ticks the Approve box and saves the file in Obsidian.

The indexer's `POST /promote` endpoint scans every `Research/*.md`,
detects ticked `**Approve:**` or `**Dismiss:**` lines, reads the
`research_query_id` from frontmatter, and HTTP-calls TradingView's
`/v1/research/queries/{id}/{approve|dismiss}`. The indexer stamps an
`<!-- vault-indexer:applied -->` banner so subsequent passes don't
re-fire the same action.

TradingView's approve route re-validates the DSL (defense in depth), then
patches the hypothesis row's `invalidator`. Next nightly hypothesis tick
re-evaluates with the new threshold.

## Auto-stress weekly task

Wired into `app/main.py` lifespan as `research-weekly`. Sleeps
`RESEARCH_WEEKLY_WARMUP_SECONDS` (default 1 hr) after boot, then fires
`run_once()` every `RESEARCH_WEEKLY_SLEEP_SECONDS` (default 7 days).

`run_once`: for each active hypothesis, call `service.ask` with the
default counterargument-style query, append a one-liner to the vault's
`_review-queue.md`. Failure on one hypothesis logs + skips, doesn't
break the others.

## Cost surface

Each response carries `tokens_in`, `tokens_out`, `est_cost_usd`. Pricing
defaults match Claude Sonnet 4.6 list pricing; override via env:
- `CLAUDE_MODEL` (default `claude-sonnet-4-6`)
- `CLAUDE_INPUT_COST_PER_MTOK` (default 3.00)
- `CLAUDE_OUTPUT_COST_PER_MTOK` (default 15.00)
- `CLAUDE_CACHE_READ_COST_PER_MTOK` (default 0.30)

System prompt + bundle prefix carry `cache_control: {type: "ephemeral"}`
so repeat queries on the same hypothesis pay the cache-read rate on the
prefix. **No daily token budget** — solo-operator volume doesn't justify
the guardrail. If usage scales, add one.

## Schema — `migrations/versions/0023_research_queries.py`

```sql
research_queries(
  id UUID PK, asked_at TIMESTAMPTZ,
  query TEXT, hypothesis_ids JSON,
  answer_path TEXT, verdict TEXT,
  tokens_in INT, tokens_out INT, est_cost_usd NUMERIC(10,6),
  bundle JSON, response JSON,
  status ('pending'|'approved'|'dismissed'|'error'),
  approved_at TIMESTAMPTZ, approved_action JSON
)
```

## Files

| | |
|---|---|
| `app/research/__init__.py` | package |
| `app/research/models.py` | `ResearchQuery` ORM |
| `app/research/schemas.py` | `AskRequest`, `AskResponse`, list/detail |
| `app/research/bundle.py` | hypothesis/evidence/macro/accuracy assembly + truncation |
| `app/research/prompts.py` | system prompt + one-shot example + bundle template |
| `app/research/client.py` | Anthropic SDK wrapper + cost calc |
| `app/research/service.py` | orchestrator: bundle → call → validate → render → persist |
| `app/research/rendering.py` | markdown answer template |
| `app/research/routes.py` | HTTP surface |
| `app/research/weekly.py` | background auto-stress loop |
| `tools/vault_indexer/research_hook.py` | tick scanner + TradingView caller |

## Frontend (Phase 3.7 — shipped 2026-05-02)

`/research` page in the React app. Single-turn UI on top of the same
`POST /v1/research/ask` + GET/approve/dismiss endpoints — markdown
files keep getting written for archival + weekly auto-stress.

| File | Role |
|---|---|
| `frontend/src/pages/Research.tsx` | page shell |
| `frontend/src/components/research/AskInput.tsx` | textarea + scope chips (active hypotheses) + submit |
| `frontend/src/components/research/AnswerCard.tsx` | verdict (markdown) + evidence list + proposed action + cost |
| `frontend/src/components/research/EvidenceItemRow.tsx` | one row per excerpt; clickable `obsidian://` deep link; expand-to-read |
| `frontend/src/components/research/ProposedActionCard.tsx` | proposed-action block with Approve/Dismiss |
| `frontend/src/components/research/ConfirmApproveModal.tsx` | two-step confirm — shows current vs proposed invalidator JSON |
| `frontend/src/components/research/HistoryList.tsx` | paginated past queries with status filter chips |
| `frontend/src/hooks/use-api.ts` | `useResearchAsk` / `useResearchQueries` / `useResearchQuery` / `useApproveResearchQuery` / `useDismissResearchQuery` |

Backend addition for v1: `AskResponse` and `ResearchQueryRead` now
return `evidence` (flat `EvidenceItem[]`) + `macro_state` +
`proposed_action`. Pulled from the persisted `bundle` / `response`
columns at read-time — UI never has to parse the bundle envelope.

## Out of scope (parked in roadmap as 8b.3–8b.9)

- `/research/digest` synthesis mode
- Action kinds: `cancel_hypothesis`, `create_opportunity`
- Telegram digest of unread answer files
- Cross-hypothesis stress (one query, multiple theses)
- Multi-LLM cross-check (Claude + GPT)
- Streaming responses (Phase 3.6 if pulled forward)
- Multi-turn threading (Phase 3.8)
- Free-form open chat over the corpus (operator uses Claude API directly)
