# Phase 3.8 — Research UI v2 (threading)

> **Status:** Direction notes only. Do not promote to a full plan until
> Phase 3.7 has been used for at least a week AND the operator hits
> the trigger condition (below).
> **Predecessor:** Phase 3.7 (single-turn UI). Threading is purely
> additive on top — same backend tool-use schema, same evidence
> bundle shape, same approval flow.

## Trigger condition

Promote this from "direction" to "executable plan" when:

> **The operator runs ≥3 queries against the same hypothesis within
> a single 7-day window AND wishes those answers had context of each
> other.**

Concrete signal: operator finds themselves typing things like "as I
asked yesterday about X, now I want to know Y" and getting answers
that don't reference yesterday's verdict. That's the moment.

If the operator goes a month with mostly one-shot queries → don't
build threading. Single-turn is enough.

## What threading is

Multi-turn conversation where each new question carries forward:
- Prior verdicts in the same thread (compressed if needed)
- Prior evidence already shown (don't re-retrieve the same chunks
  unless query genuinely shifts)
- Prior proposed actions and their approval status (so a turn can ask
  "given the threshold I tightened yesterday, what's left at risk?")

Conceptually: a thread is a *focused investigation* of one hypothesis
or one cross-cutting question. Threads end when the operator hits
"new thread" or starts on a different hypothesis.

## What changes

### Backend

**Schema (migration `0024_research_thread_id`):**

```sql
ALTER TABLE research_queries
  ADD COLUMN thread_id UUID;
CREATE INDEX ix_research_queries_thread_id
  ON research_queries (thread_id, asked_at);
```

`thread_id NULL` means "not part of a thread" (legacy + one-off
queries). New queries get a thread_id from the operator's "continue
this thread" / "new thread" UI choice.

**Bundle assembler (`app/research/bundle.py`):**

When `thread_id` is set, prepend a transcript of prior turns to the
LLM input. Two strategies, pick at build time:

1. **Verbatim recent turns.** Last 3 turns inline (operator query +
   verdict + tool call). Fast, accurate, ~2-3k tokens overhead.
2. **Compressed older turns.** When ≥4 prior turns, summarise turns
   1..N-3 via Haiku ("the operator has previously established: ..."),
   keep last 3 verbatim. Caps prompt size; ~$0.001 per compression.

Default: strategy 1 until threads exceed 6 turns; flip to strategy 2
above that threshold.

**Cache impact:** prompt-cache hit-rate drops on multi-turn paths
because the user-message-tail changes per turn. Expected; the
*system prompt + bundle prefix* still cache-hits across turns. Net
cost per turn: ~30% higher than single-turn but still pennies.

**API:**

```
POST /v1/research/ask                           creates a NEW thread by default
POST /v1/research/threads                       create empty thread, return thread_id
POST /v1/research/threads/{thread_id}/ask       append a turn to existing thread
GET  /v1/research/threads/{thread_id}           full thread with all turns
GET  /v1/research/threads                       list threads (paginated)
```

`AskRequest` gains `thread_id: Optional[str]`. When set, the request
goes to the thread-append path; bundle assembler reads prior turns.

### Frontend

**Page reshape:**

The Research page becomes thread-shaped:

```
┌──────────────────────────────────────────────────────────────┐
│  Threads             │  Active thread: btc-bottom risk       │
│  ──────────          │  ───────────────────────────────────  │
│  + New thread        │  [Turn 1, 2 days ago]                 │
│                      │   Q: what's at risk in my BTC ...     │
│  • btc-bottom risk   │   A: thesis weakening...              │
│    (4 turns, 2d ago) │   [evidence] [action: pending]        │
│  • stagflation drift │                                        │
│    (2 turns, 6h ago) │  [Turn 2, 6 hours ago]                │
│  • inflation watch   │   Q: did the DXY threshold I tighten...│
│    (1 turn, 12h ago) │   A: ...                              │
│                      │                                        │
│  History (closed)    │  ┌────────────────────────────────┐  │
│  ...                 │  │ Ask a follow-up...             │  │
│                      │  └────────────────────────────────┘  │
│                      │  [Submit]   [End thread]              │
└──────────────────────────────────────────────────────────────┘
```

Threads list on the left. Active thread on the right with all turns
stacked. Same AnswerCard + EvidenceItemRow + ProposedActionCard
components from v1 — they render per turn instead of in a single
top-of-page slot.

**Components added on top of v1's:**
- `ThreadList.tsx` — left pane
- `ThreadView.tsx` — right pane (renders N AnswerCards + a follow-up
  AskInput at the bottom)
- `ThreadEmptyState.tsx` — when no active thread

**Hooks added:**
- `useThreads()` — list
- `useThread(id)` — single with turns
- `useCreateThread()` — POST /research/threads
- `useResearchAsk` mutation gains `thread_id` in payload

### Risks worth flagging now

1. **Token bloat per thread.** A 10-turn thread with no compression is
   ~30k input tokens per turn. Mitigation: compression strategy 2 at
   ≥4 prior turns. Hard cap: refuse to append at 15 turns; force the
   operator to start a new thread (with a "summarise this thread to
   start a new one" button as escape hatch).
2. **Cache miss on every turn.** Solvable but real. Each turn is a
   different prompt suffix, so only the system + bundle prefix cache.
   Expect ~2× cost per turn vs single-turn. Pennies, but real.
3. **Approve-button blast inside a thread.** Approving an action mid-
   thread should not break the thread. The thread keeps going; the
   hypothesis state is now post-approve; subsequent turns reflect that.
   Test this carefully — the approval should mutate the hypothesis
   AND continue the thread cleanly.
4. **Operator confusion: "is this a new thread or a follow-up?"**
   UI must make this explicit. Default behaviour: typing a question
   from the Research-page-root creates a NEW thread; appending only
   happens from inside an active thread.
5. **Threading interacts with weekly auto-stress.** Auto-stress fires
   per active hypothesis. Should those land in NEW threads each week,
   APPEND to a single "<hypothesis> stress" thread, or be one-offs
   (the current behaviour)? Direction: keep auto-stress one-off;
   threading is operator-initiated. Auto-stress files still land in
   `Research/`, threads live separately.

### Effort estimate (when triggered)

- Migration 0024 + thread_id wiring: 1 hr
- Bundle assembler thread-aware: 2 hrs
- 4 new endpoints + tests: 2 hrs
- Frontend page reshape: 4 hrs
- ThreadList + ThreadView + follow-up input: 2 hrs
- Compression strategy + token cap: 2 hrs
- E2E smoke + polish: 1 hr
- **Total: ~14 hrs.** ~2 sessions.

## What NOT to design now

These can wait until Phase 3.8 actually starts:

- Auto-summarise stale threads after N weeks
- Search across thread bodies
- Export a thread to markdown / PDF
- Multi-hypothesis threads (thread spans 2+ theses) — likely never
  needed; if it comes up, it's a sign the question shape is wrong
- Streaming inside thread turns (Phase 3.6 territory; orthogonal)
- Per-thread cost budget separate from per-query

## When you pick this up

Read this file + Phase 3.7's plan + ADR-015 first. Threading is
*additive* — every Phase 3.7 component should still work, with
threading layered on top. If you find yourself rewriting Phase 3.7
shapes, that's a sign the design is drifting.

The riskiest assumption to validate during early Phase 3.8 use:
**that operator-initiated threads, not auto-stress chains, drive
value.** If after 2 weeks the operator has 0-1 manually-created
threads, threading was the wrong call and we're back to single-turn
+ auto-stress. Don't sink another phase into this — admit the miss.
