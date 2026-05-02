# Phase 3.7 — Research UI v1 (single-turn)

> **Status:** READY TO BUILD. Brainstormed + scoped 2026-05-02. Self-contained — no re-planning needed.
> **Predecessor:** Phase 3 backend (commit `2fe5ddf`) — `POST /v1/research/ask` already works, persists rows, writes markdown into `<vault>/Research/`. This phase is the operator-facing UI on top.
> **Successor (NOT this phase):** Phase 3.8 threading. Direction-only notes at [`phase-3.8-research-ui-threading.md`](phase-3.8-research-ui-threading.md).

## Picking this up in a new session

This file is self-contained. **Don't re-plan or re-brainstorm.** The
design is locked. Pickup pattern:

1. Read this file end to end.
2. Confirm `pytest -q` is green (baseline ~343).
3. Start the vault-indexer (background, `uvicorn tools.vault_indexer.app:app --port 8001`) — Phase 3.7 doesn't change indexer code, but the UAT smoke calls it.
4. Execute the "Suggested execution order" section (last section in this file) step by step.
5. Commit at end. UAT (10 steps) before commit.

If you hit a blocker (missing dep like `react-markdown`, schema conflict, indexer not starting) — pause and ask the operator before improvising. Most likely blocker: `react-markdown` not yet installed; fall back to plain text + file backlog item.

**State of the world at pickup time** (everything below is already shipped, do NOT touch):

- Phase 1 / M-2: hypothesis object + invalidator DSL + daily lifespan tick (commit `663048a`)
- Phase 2: vault + indexer sidecar + 6 hypothesis seeds + DSL invalidators applied (commits `89c1ab3`, `b56fde0`)
- Phase 3 backend: `/v1/research/ask` + `propose_invalidator_update` tool-use + weekly auto-stress + indexer Research-tick promotion (commit `2fe5ddf`)
- The Intelligent Investor: 20 chapters, 416 embedded chunks, fully searchable (commit `1cd9acf` for the review-queue bug fix that was the last issue)
- Source-breadcrumb in PDF/EPUB ingest, layout-aware splitter, taxonomy with `investing_classics` (commits `16acd7e`, `a61bac0`)
- Background-task gating in tests (`DISABLE_LIFESPAN_BACKGROUND_TASKS=1` in conftest, commit `7251435`)
- `Base.metadata.create_all` removed from lifespan + boot-time schema-drift WARN (commit `d6b4cb6`)

You don't need any of this loaded into context to execute Phase 3.7. The plan below references the exact file paths you'll touch.

## Context

Phase 3 ships the stress-test loop in markdown form: operator runs
`/v1/research/ask` (or weekly auto-stress fires it), the answer lands
as a markdown file in `<vault>/Research/`, operator opens in Obsidian,
ticks Approve, the indexer's `/promote` flow back-calls TradingView.

That works but adds friction:
- Operator has to keep an Obsidian window open alongside the TradingView app
- Approve requires saving the file (the indexer's watch loop fires
  on save), introducing a 1-2 second latency
- The UI shows "research" nowhere — zero discoverability for a
  capability that's the unique-wedge of the platform

UI v1 puts the loop inside the app. **Markdown answer files keep
getting written** (archival, vault-indexable, weekly-auto-stress
target) — the UI is a complementary surface, not a replacement.

## Locked decisions (from brainstorm)

1. **Single-turn only.** No threading in v1. Threading is Phase 3.8,
   gated on operator hitting the concrete "asked the same hypothesis
   3+ times this week and wished the answers knew about each other"
   moment.
2. **Open-chat is out of scope** (parked at 8b.10). Operator uses the
   Claude API directly for open-ended discussion.
3. **Confirm-modal on Approve.** Operator's Phase 3 design deliberately
   put the action behind a tickable markdown checkbox so there's an
   inspectable artifact. The UI button is one click — same effect, less
   inspectable. A two-step modal (preview the patch payload, then
   click Approve) matches the seriousness of mutating hypothesis DSL.
4. **AskResponse gains `evidence`.** Today the response has only
   verdict + proposed_action; the evidence list lives in the row's
   `bundle` JSON. UI needs the evidence flat in the response so it
   can render without a second call.
5. **History list uses existing `/v1/research/queries`.** No new
   endpoint. Filter by status (`pending` / `approved` / `dismissed`).
6. **Auto-refresh after submission.** No streaming for v1 — submit is
   a blocking call. Latency is ~3-8s; operator sees a spinner. If this
   feels long after a week of use, Phase 3.6 (streaming) gets pulled
   forward.

## Backend changes

### 1. Extend `AskResponse` with `evidence`

[`app/research/schemas.py`](../../app/research/schemas.py):

```python
class EvidenceItem(BaseModel):
    vault_path: str
    title: Optional[str] = None
    section: Optional[str] = None
    text: str                 # excerpt body, truncated to ~600 chars
    similarity: float
    decay_weight: float
    score: float
    published_at: Optional[str] = None
    author: Optional[str] = None


class MacroSnapshotItem(BaseModel):
    symbol: str
    latest: float
    latest_ts: str


class AskResponse(BaseModel):
    query_id: str
    answer_path: Optional[str]
    verdict: Optional[str]
    tokens_in: int
    tokens_out: int
    est_cost_usd: float
    proposed_action: Optional[dict[str, Any]] = None
    status: str
    # NEW — populated from the bundle so the UI doesn't need a second call.
    evidence: list[EvidenceItem] = Field(default_factory=list)
    macro_state: list[MacroSnapshotItem] = Field(default_factory=list)
```

### 2. Populate `evidence` in `service.ask`

[`app/research/service.py`](../../app/research/service.py) — at the end
of `ask()`, before the return dict:

```python
return {
    "query_id": research_query_id,
    "answer_path": answer_path_rel,
    "verdict": result.verdict_text,
    "tokens_in": result.tokens_in,
    "tokens_out": result.tokens_out,
    "est_cost_usd": float(result.est_cost_usd),
    "proposed_action": proposed_action,
    "status": _models.STATUS_PENDING,
    # NEW
    "evidence": [
        {
            "vault_path": e["vault_path"],
            "title": e.get("title"),
            "section": e.get("section"),
            "text": (e.get("text") or "")[:600],
            "similarity": e.get("similarity", 0.0),
            "decay_weight": e.get("decay_weight", 1.0),
            "score": e.get("score", 0.0),
            "published_at": e.get("published_at"),
            "author": e.get("author"),
        }
        for e in (bundle.get("evidence") or [])
    ],
    "macro_state": [
        {"symbol": sym, "latest": info["latest"], "latest_ts": str(info.get("latest_ts", ""))}
        for sym, info in (bundle.get("macro_state") or {}).items()
        if isinstance(info, dict) and "latest" in info
    ],
}
```

### 3. `GET /v1/research/queries/{id}` returns the same enriched shape

So that history items can be re-rendered without recomputing. Pull
evidence + macro_state out of the persisted `bundle` column on read.

[`app/research/routes.py`](../../app/research/routes.py): change
`get_query` to construct an enriched `ResearchQueryRead` (extend the
schema to include `evidence` + `macro_state` + `proposed_action`).

### 4. Tests

Extend [`tests/test_research.py`](../../tests/test_research.py):
- `test_ask_response_includes_evidence_when_bundle_has_excerpts` — set
  up a fake bundle with one excerpt; assert response.evidence has
  exactly one item with the right vault_path / score.
- `test_get_query_returns_enriched_shape` — same shape on the GET path.

## Frontend changes

### 1. New page

[`frontend/src/pages/Research.tsx`](../../frontend/src/pages/Research.tsx):

```tsx
export function Research() {
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState<string[]>([])  // empty = all active
  const ask = useResearchAsk()
  const queries = useResearchQueries({ limit: 30 })

  const onSubmit = () => ask.mutate({ query, hypothesis_slugs: scope.length ? scope : undefined })

  return (
    <div className="space-y-6">
      <Card><AskInput onSubmit={onSubmit} ... /></Card>
      {ask.data && <AnswerCard response={ask.data} />}
      <Card><HistoryList items={queries.data?.items ?? []} /></Card>
    </div>
  )
}
```

### 2. Components under `frontend/src/components/research/`

**`AskInput.tsx`** — textarea + scope chips + submit button. Scope
chips fed by `useHypotheses({ status: 'active' })`. Submit disabled
while `ask.isPending`. Show spinner on the button during the call.

**`AnswerCard.tsx`** — top-level card with:
- Verdict (markdown rendered via existing `react-markdown` or simple
  paragraph if not installed — check)
- Evidence list (renders `EvidenceItemRow` per item)
- Proposed action card (renders `ProposedActionCard` if present)
- Cost line at the bottom

**`EvidenceItemRow.tsx`** — one chip per evidence item:
- Vault path (clickable → opens via `obsidian://open?vault=knowledge-vault&file=<path>` URI scheme)
- Score / decay-weight badges
- Excerpt text on hover or expand

**`ProposedActionCard.tsx`** — proposed action block:
- Hypothesis slug chip
- Op + args (rendered as a small JSON-ish block)
- Rationale + confidence
- `[Approve]` and `[Dismiss]` buttons. Approve opens
  `ConfirmApproveModal`.

**`ConfirmApproveModal.tsx`** — modal showing:
- Hypothesis being mutated (slug + current invalidator)
- Proposed invalidator (full JSON)
- Confidence
- "Apply" + "Cancel" buttons. Apply calls `useApproveResearchQuery`.

**`HistoryList.tsx`** — paginated list of past queries:
- Date + query (truncated) + hypothesis chips + status badge
- Click expands to show that query's full AnswerCard
- Status filter chips at top: `all` / `pending` / `approved` / `dismissed`

### 3. Hooks

[`frontend/src/hooks/use-api.ts`](../../frontend/src/hooks/use-api.ts):

```ts
export function useResearchAsk() {
  const { backendId } = useBackend()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AskRequest) =>
      apiFetch<AskResponse>('/v1/research/ask', { method: 'POST', body: payload, backendId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['research-queries', backendId] })
    },
  })
}

export function useResearchQueries(params?: { limit?: number; offset?: number; status?: string }) {
  const { backendId } = useBackend()
  return useQuery({
    queryKey: ['research-queries', backendId, params],
    queryFn: () => {
      const s = new URLSearchParams()
      if (params?.limit) s.set('limit', String(params.limit))
      if (params?.offset) s.set('offset', String(params.offset))
      if (params?.status) s.set('status', params.status)
      const qs = s.toString() ? `?${s}` : ''
      return apiFetch<ResearchQueriesList>(`/v1/research/queries${qs}`, { backendId })
    },
    staleTime: 30_000,
  })
}

export function useResearchQuery(id: string | null | undefined) { ... }
export function useApproveResearchQuery() { ... }   // POST /queries/{id}/approve
export function useDismissResearchQuery() { ... }   // POST /queries/{id}/dismiss
```

### 4. Types

[`frontend/src/lib/types.ts`](../../frontend/src/lib/types.ts) gains:

```ts
export interface EvidenceItem { vault_path; title?; section?; text; similarity; decay_weight; score; published_at?; author? }
export interface MacroSnapshotItem { symbol; latest; latest_ts }
export interface AskRequest { query; hypothesis_slugs?: string[] }
export interface AskResponse {
  query_id; answer_path; verdict; tokens_in; tokens_out; est_cost_usd;
  proposed_action; status;
  evidence: EvidenceItem[]; macro_state: MacroSnapshotItem[];
}
export interface ResearchQueryRead { ... }   // matches backend schema
export interface ResearchQueriesList { items: ResearchQueryRead[]; count: number }
```

### 5. Routing + sidebar

[`frontend/src/App.tsx`](../../frontend/src/App.tsx) — lazy route
`/research` → `Research` page.

[`frontend/src/components/Layout.tsx`](../../frontend/src/components/Layout.tsx)
— sidebar nav entry under the "Decisions" group, between Predictions
and Watchlists:

```tsx
{ path: '/research', label: 'Research' },
```

Use a search/lightbulb-y icon (lucide-react has `Search` and `Sparkles`).

### 6. Frontend tests

Per the existing pattern, add a test file
`frontend/__tests__/Research.test.tsx` (or wherever the Vite test
setup lives — operator may not have one yet; if no test infra, file a
backlog item rather than build it for this phase).

If test infra exists, cover:
- Renders empty state when no answer yet
- Renders verdict + evidence + action card after a successful ask
- Approve button opens modal; modal Apply calls the approve endpoint
- Dismiss button hits the dismiss endpoint
- History list renders + filters by status

## Effort

| Step | Effort |
|---|---|
| Backend AskResponse extension + service.py + schema.py edits | 1 hr |
| GET /queries/{id} enriched return | 30 min |
| Backend tests (+2) | 30 min |
| Frontend types | 15 min |
| Frontend hooks (5 of them) | 30 min |
| Research page shell + AskInput + sidebar wiring | 1.5 hrs |
| AnswerCard + EvidenceItemRow | 1 hr |
| ProposedActionCard + ConfirmApproveModal | 1 hr |
| HistoryList with status-filter chips | 1 hr |
| End-to-end smoke + polish | 1 hr |
| **Total** | **~7-8 hrs** |

## UAT (what "Phase 3.7 ships" means)

1. `pytest -q` green (350 baseline + 2 new = 352 expected; if any
   regressions — backend AskResponse extension is the suspect).
2. From the Research page: type "what's at risk in my BTC bottom
   thesis?", scope to `btc-bottom-3m`, hit Ask → spinner → answer
   appears within ~10s with verdict text + ≥1 evidence item with
   non-zero similarity + proposed action card.
3. The same query lands a markdown file in `<vault>/Research/` with
   the same `research_query_id` as the row.
4. Click an evidence path → opens the source note in Obsidian via
   `obsidian://` URI.
5. Click Approve on the proposed action → confirm modal shows the
   exact patch JSON → Apply → toast success → hypothesis row's
   invalidator is updated (verify via `/v1/hypotheses/{slug}`).
6. Refresh page → query appears in History list with status `approved`.
7. Dismiss flow on a separate query → status `dismissed`.
8. Tab away to /predictions, come back → history list still loads.
9. Close indexer (`pkill uvicorn`) → submit a new query → response
   still works (bundle's evidence will be empty but no crash).
10. Restart indexer → next query has full evidence again.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `react-markdown` not installed (verdict needs markdown rendering) | L | Check `frontend/package.json`. If absent, add `react-markdown` + `remark-gfm`. Or render plain text for v1 — verdict is short. |
| Indexer not running at submit time → empty evidence | L | Backend already handles this gracefully (bundle has empty evidence list); UI shows "no evidence retrieved" + a hint to start the indexer. |
| Approve confirm-modal feels heavy | M | If after 1 week of use it feels in the way, downgrade to a single-step button. Easy to toggle. |
| Latency feels long without streaming | M | Spinner makes it visible; if a week of use feels painful, pull Phase 3.6 (streaming) forward. |
| HistoryList fetches too eagerly on page focus | L | `staleTime: 30_000` already debounces. Tune if needed. |

## Files (summary)

**Backend (~80 lines edited / added):**
- `app/research/schemas.py` — extend AskResponse + ResearchQueryRead
- `app/research/service.py` — populate evidence + macro_state
- `app/research/routes.py` — enrich `get_query` return
- `tests/test_research.py` — +2 tests

**Frontend (~700 lines new):**
- `frontend/src/pages/Research.tsx`
- `frontend/src/components/research/{AskInput,AnswerCard,EvidenceItemRow,ProposedActionCard,ConfirmApproveModal,HistoryList}.tsx`
- `frontend/src/lib/types.ts` — types
- `frontend/src/hooks/use-api.ts` — hooks
- `frontend/src/App.tsx` — lazy route
- `frontend/src/components/Layout.tsx` — sidebar entry

**Docs:**
- `.claude/research.md` — add "Frontend" section
- `.claude/roadmap-shipped.md` — append entry once Phase 3.7 ships

## Out of scope (Phase 3.8 territory or later)

- Threading / multi-turn — Phase 3.8 (8b.9), see direction notes
- Streaming responses — Phase 3.6 (8b.6 if pulled forward)
- Free-form open chat — OUT OF SCOPE (use Claude API directly)
- Inline source-content viewer (read the chunk in-app instead of via
  Obsidian) — only if Obsidian-deep-link feels too clunky after use
- Approve-without-modal "fast" mode — only if confirm-modal feels in
  the way

## Suggested execution order (when you pick this up next session)

1. Backend first: schema + service + tests. Get evidence flowing into
   AskResponse. Verify with curl. ~1.5 hrs.
2. Hooks + types: get the frontend talking to the new shape. ~45 min.
3. Page shell + AskInput + sidebar entry: prove the page loads + ask
   works end-to-end with a hardcoded scope. ~1.5 hrs.
4. AnswerCard + EvidenceItemRow: render a real response. ~1 hr.
5. Proposed action + confirm modal + approve/dismiss: complete the
   loop. ~1.5 hrs.
6. HistoryList: cherry on top. ~1 hr.
7. Smoke test against your real `btc-bottom-3m` query. Polish. Commit.

This is a **single-session** build for an unblocked operator with
context. If you stall, the most likely culprit is `react-markdown`
not being installed — fall back to plain text and add it as a backlog
item.
