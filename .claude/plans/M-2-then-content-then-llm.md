# Plan — M-2 → Content Layer → Hybrid LLM Stack

> **Roadmap-level plan.** Three phases, sequenced. Each phase's full plan lives in its own file (M-2 already drafted; Phase 2 + 3 detailed below).
> **Status:** awaiting operator approval to execute Phase 1.

## Context

Operator has shipped M-1 (macro series + ratios). Three phases follow, each enables the next:

1. **M-2 — Hypothesis object** ([.claude/plans/M-2-hypothesis-object.md](M-2-hypothesis-object.md)). The hook every downstream layer attaches to. Without it, content + LLM have nothing structured to reason about.
2. **Content layer.** Operator-curated reading material attached to hypotheses. Two ingestion classes (timeless and timely-with-decay).
3. **Hybrid LLM stack.** Local for embeddings/transcription; Claude API for reasoning + structured action recommendations against the operator's existing API surface.

The through-line: M-2 makes beliefs queryable → content layer attaches *evidence* to those beliefs → LLM stack synthesizes evidence + state into reviewable suggestions. Each phase is useful standalone but compounds with the next.

---

## Phase 1 — M-2 (hypothesis object + view registry)

**See:** [.claude/plans/M-2-hypothesis-object.md](M-2-hypothesis-object.md) — full plan, schema, DSL, tests, UAT.

**Recap of scope:** `hypothesis` + `hypothesis_evaluation` tables; 5-op invalidator DSL; daily lifespan tick (TTL → evaluate → cascade); view registry as parsed markdown files; `/v1/hypotheses` + `/v1/views` routes; frontend `/hypotheses` page; seed script for the 5 existing drafts.

**Adjustment from operator decision (brainstorm 2026-05-01):** ship the page small. Backend + seed + a sidebar "active hypotheses" widget first. Defer the full `/hypotheses` page until ≥10 active rows justify it. This trims ~30% of frontend work without blocking Phase 2.

**Phase 1 exit criteria (must pass before Phase 2 begins):**
- All Phase 1 UAT in M-2 plan (steps 1–6, 8, 9) green.
- Sidebar widget shows active count + at-risk count (1 query, 1 component).
- `GET /v1/hypotheses?status=active` returns the 5 seeded rows.

---

## Phase 2 — Content Layer

### Goal

A small, local table of operator-curated reading material, each item attached to one or more hypotheses, retrievable by similarity for downstream LLM bundling. **Not NotebookLM** — content lives in the operator's DB, queryable from anywhere on the platform.

### Two ingestion classes (operator-defined)

| Class | Source | Cadence | Size | Decay |
|---|---|---|---|---|
| **A — Timeless** | PDFs, EPUBs (books, papers, foundational reports) | Variable; whenever operator uploads | Larger (10s–100s of pages) | None — `expires_at = NULL`, retrieval weight constant |
| **B — Timely** | Weekly newsletters + expert commentary videos | Roughly weekly | Small per item, but consistent volume | Yes — content states its own horizon, retrieval weight decays |

### Schema — `migrations/versions/0022_content_items.py`

```sql
CREATE TABLE content_items (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  kind TEXT NOT NULL CHECK (kind IN ('timeless', 'timely')),
  source TEXT NOT NULL CHECK (source IN ('pdf', 'epub', 'newsletter', 'video', 'article')),
  source_url TEXT NULL,                   -- where it came from (nullable: local upload)
  title TEXT NOT NULL,
  author TEXT NULL,                        -- expert/publication name; matters most for class B
  published_at DATE NULL,                  -- when the *content* was created (not ingested)
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Class B only: operator-stated or content-stated horizon. Drives decay.
  horizon_months INT NULL,
  -- Free-form taxonomy: 'energy', 'liquidity', 'btc', etc. Indexed for filtering.
  themes TEXT[] NOT NULL DEFAULT '{}',
  -- Links to hypotheses this item supports/challenges. M:N via join table.
  -- (separate table below for atomic add/remove)
  raw_text TEXT NOT NULL,                  -- normalized full text (post-OCR/transcription)
  metadata JSONB NOT NULL DEFAULT '{}'     -- source-specific bag (page count, video duration, etc.)
);

CREATE INDEX content_items_kind_published ON content_items (kind, published_at DESC);
CREATE INDEX content_items_themes_gin ON content_items USING gin (themes);

CREATE TABLE content_hypothesis_links (
  content_id UUID NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  hypothesis_id UUID NOT NULL REFERENCES hypothesis(id) ON DELETE CASCADE,
  stance TEXT NOT NULL CHECK (stance IN ('supports', 'challenges', 'context')),
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (content_id, hypothesis_id)
);

CREATE TABLE content_excerpts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  content_id UUID NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  ord INT NOT NULL,                        -- chunk order within the item
  text TEXT NOT NULL,
  -- Optional structural metadata: chapter title, video timestamp, etc.
  section TEXT NULL,
  embedding vector(384) NULL,              -- pgvector; BGE-small-en-v1.5 is 384-dim
  UNIQUE (content_id, ord)
);

CREATE INDEX content_excerpts_embedding_ivfflat
  ON content_excerpts USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

**Notes:**
- `pgvector` extension required on Railway Postgres. Already supported on Railway's standard Postgres plugin via `CREATE EXTENSION vector;`. SQLite test parity: skip embedding column in test fixtures or use `sqlite-vec` (defer — tests can mock embeddings).
- `vector(384)` matches BGE-small-en-v1.5. Switching to a larger model later requires a migration (cheap — re-embed).
- Hypothesis links are M:N with explicit `stance` so a single article can support thesis A while challenging thesis B.

### Ingestion pipelines (laptop-only — MLX needed)

Operator runs ingestion on the laptop primary. Output (text + embeddings) syncs to Railway via the existing outbox (new outbox `kind`: `content_item`, `content_excerpt`, `content_link`).

#### Class A — PDF / EPUB

`scripts/ingest_content.py --kind=timeless --path=<file>`:

1. Parse text — `pymupdf` for PDF, `ebooklib` for EPUB.
2. Chunk — ~600 tokens with 80-token overlap. Section-aware: include chapter/heading in `section` field per chunk.
3. Embed — local BGE-small-en-v1.5 via MLX (one model load per ingestion run).
4. Insert `content_items` + `content_excerpts` rows.
5. Operator follow-up via UI: link to hypotheses, tag themes.

#### Class B — Newsletter / Video

`scripts/ingest_content.py --kind=timely --source=video|newsletter --url=<url>`:

1. Fetch — `yt-dlp` audio-only for video; `readability-lxml` for newsletter URL; or `--text-file` for paste.
2. Transcribe (video only) — MLX-Whisper-large-v3 or whisper.cpp. Cache transcript by video ID.
3. Chunk — ~400 tokens with 50-token overlap. Smaller than Class A because timely content is denser per chunk.
4. Embed — same BGE-small.
5. Extract `published_at` and `horizon_months`:
   - `published_at` from feed metadata or video upload date.
   - `horizon_months` from operator at ingestion time (`--horizon=6`) — script prompts if absent. Future enhancement: extract from text via lightweight LLM call.
6. Insert + link to hypotheses (operator picks at ingestion time via `--hypothesis-slug=...`).

### Decay model (Class B retrieval weighting)

Retrieval at LLM-bundle time uses a **decayed similarity score**:

```
score = cos_sim(query, excerpt) * decay_weight(item)

decay_weight(item) =
  1.0                                         if kind = 'timeless'
  exp(-age_months / (horizon_months / 2))     if kind = 'timely' and horizon_months IS NOT NULL
  exp(-age_months / 6)                        if kind = 'timely' and horizon_months IS NULL
```

Half-life = `horizon_months / 2`. A 12-month-horizon piece weights ~0.71 at 6 months old, ~0.5 at 12 months, ~0.25 at 24 months. Defaults to a 6-month half-life for class-B items missing an explicit horizon.

**Status pill** in UI for operator awareness:
- `fresh`: age < horizon × 0.3
- `aging`: horizon × 0.3 ≤ age < horizon × 1.0
- `stale`: age ≥ horizon × 1.0 (operator may want to archive)

No automatic deletion. Decay is retrieval-side; the row lives forever in case operator wants to re-link or audit.

### Routes

```
GET  /v1/content                          list (filter: kind, theme, hypothesis_id, fresh|aging|stale)
GET  /v1/content/{id}                     full item + excerpts
POST /v1/content                          minimal create (operator-authored stub; ingestion script the main path)
PATCH /v1/content/{id}                    edit themes, horizon, hypothesis links
DELETE /v1/content/{id}                   cascades excerpts + links
POST /v1/content/{id}/links               attach to a hypothesis with stance
DELETE /v1/content/{id}/links/{hyp_id}    unlink
GET  /v1/content/search?q=...&k=10        retrieval endpoint — embeds query, returns top-k excerpts with score
```

`/v1/content/search` is the endpoint the LLM bundle consumes in Phase 3.

### Frontend

Minimum viable UI for Phase 2:
- New page `/content` — list with filter chips (kind, theme, status pill for class B).
- Row click → drawer with full text + linked hypotheses + per-excerpt list.
- "Attach to hypothesis" action — multi-select hypothesis picker, stance toggle.
- On the existing `/hypotheses` widget/page (Phase 1): show count of linked content items per hypothesis.

Defer fancier surfacing (timeline view, theme cloud) to a follow-up.

### Tests

- Schema migration applies + rolls back cleanly.
- Ingestion (class A): given a 10-page PDF fixture, produces N excerpts with embeddings of correct dim.
- Ingestion (class B): given a fake transcript text, parses horizon, computes decay weight at multiple ages.
- Decay weight at boundaries: timeless = 1.0; timely with `horizon_months=NULL` = 6mo half-life; timely fresh = ~1.0; timely past horizon = <0.5.
- Retrieval: query embeds, top-k filters by hypothesis link, scores ordered.
- Routes: CRUD + link/unlink + search round-trips.

### Phase 2 exit criteria

- 3 class-A items + 3 class-B items ingested.
- Each item linked to ≥1 hypothesis with explicit stance.
- `/v1/content/search?q=stagflation&k=5` returns ranked excerpts respecting decay.
- Frontend list + drawer renders all items with correct status pills.

---

## Phase 3 — Hybrid LLM Stack

### Goal

LLM-assisted reasoning that grounds answers in *operator state* (active hypotheses + retrieved excerpts + macro context + recent predictions/accuracy) and returns *structured action suggestions* against the existing API surface. **Operator always approves** — no autonomous writes.

### Layer split

| Layer | Implementation | Reason |
|---|---|---|
| Transcription (video) | MLX-Whisper-large-v3 (laptop) | Free, private, fast on M-series. Used by Phase 2 ingestion. |
| Embeddings (ingestion + queries) | BGE-small-en-v1.5 via MLX (laptop) | Free, deterministic, no rate limit. Quality matches OpenAI's small model for English. |
| Cheap classifiers (e.g. theme tagging) | Optional: local Llama-3.1-8B via MLX | Only if operator wants auto-theming; otherwise skip. |
| **Reasoning** | **Anthropic Claude Sonnet 4.x via API** | Multi-doc synthesis, structured tool-use, financial nuance. Cost: pennies/day at solo-operator volume. |

### Bundle assembler — `app/research/bundle.py`

Single function `build_bundle(query, *, hypothesis_ids=None, k=8) -> BundlePayload`:

1. Fetch hypotheses — by `hypothesis_ids` if specified, else all `status='active'`. Pull last 3 `hypothesis_evaluation` rows per item.
2. Retrieve excerpts — call `/v1/content/search?q=<query>&k=<k>` filtered by `hypothesis_id` if provided. Apply decay weighting.
3. Macro snapshot — current values for the ratios + spreads on each linked hypothesis's `tracking_signal`.
4. Recent predictions — last 14d of accuracy stats for any tickers mentioned in hypotheses (joined via existing accuracy service).

Output:
```python
BundlePayload(
    hypotheses=[HypothesisCard(...), ...],
    excerpts=[ExcerptCard(text, source, age_months, decay_weight, score), ...],
    macro_state={"WALCL/GDP_30d_sma_diff": -0.03, ...},
    recent_accuracy={"BTC-USD": {"hit_rate": 0.62, "mape": 0.038, "n": 21}, ...},
    query=query,
)
```

### Reasoning endpoint — `POST /v1/research/ask`

Body: `{query: str, hypothesis_ids?: UUID[], structured?: bool}`.

Flow:
1. Build bundle.
2. Render bundle into a deterministic prompt template (operator can review the rendered bundle in UI before sending — debug toggle).
3. Call Claude with system prompt + bundle + query. Use `tool_use` for `recommend_action`:

```python
TOOLS = [{
    "name": "recommend_action",
    "description": "Propose ONE concrete action against the operator's API surface. Operator reviews and approves.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"enum": ["update_invalidator", "cancel_hypothesis", "create_opportunity", "no_action"]},
            "hypothesis_id": {"type": "string"},
            "rationale": {"type": "string"},
            "patch": {"type": "object"},          # shape varies by kind
            "confidence": {"type": "number"},     # 0-1
            "evidence_excerpt_ids": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["kind", "rationale", "confidence"]
    }
}]
```

4. Persist response in new `research_queries` table for audit + replay.

Response shape:
```json
{
  "query_id": "...",
  "verdict": "...",                  # free-text 1-3 sentences
  "evidence": [{"excerpt_id": "...", "weight": 0.84}, ...],
  "actions": [<ToolUseBlock>, ...],  # 0+ recommend_action calls
  "raw_tokens_in": 4123,
  "raw_tokens_out": 891
}
```

### Action approval flow

Frontend `/research` page:
- Query input + (optional) hypothesis multi-select.
- Streamed verdict text + evidence chips (click → opens excerpt in a side drawer).
- For each `recommend_action`: a card with kind / hypothesis / patch / confidence + **Approve** + **Dismiss** buttons.
- Approve → calls existing API endpoint (e.g. PATCH `/v1/hypotheses/{id}` for `update_invalidator`). Records approval in `research_queries.actions[i].approved_at`.
- Dismiss → records dismissal with optional operator-typed reason.

This gives a **fully audited path**: query → reasoning → suggested action → operator decision → API call. Replayable.

### Cost / rate guardrails

- Hard cap per query: 10k tokens in + 2k tokens out via `max_tokens` and bundle truncation if oversized.
- Per-day budget: env var `RESEARCH_DAILY_TOKEN_LIMIT` defaults 200k; lifespan tick checks `research_queries` aggregate from current UTC day; over-limit returns 429.
- Always show `tokens_in`/`tokens_out`/`est_cost_usd` next to the verdict so the operator sees marginal cost per query.

### Caching

- Bundle hash = SHA(hypotheses_state + excerpts_top_k_ids + macro_snapshot_minute + query). Cache hit returns cached response. Avoids paying twice for the same question within a tick.
- TTL: 1 hour (data changes daily anyway).

### Tests

- Bundle assembly: synthetic hypothesis + excerpts → expected payload shape.
- Decay applied correctly in retrieval.
- Cost guardrail: budget exceeded → 429.
- Tool-use round-trip: mock Claude returns 1 `recommend_action` of each kind → action persisted with status `proposed`.
- Approval path: approve `update_invalidator` → matching PATCH fires → action status `approved` → query row updated.
- Cache: same bundle hash → no second API call.

### Phase 3 exit criteria

- Operator submits query "what's at risk in my BTC thesis given recent commentary?" → bundle fires, Claude responds with verdict + ≥1 evidence excerpt + ≥1 `recommend_action` of `update_invalidator` kind.
- Operator approves the action → invalidator updated → next lifespan tick re-evaluates with new threshold.
- Daily token budget enforces; `est_cost_usd` visible in UI.

---

## Risks (across phases)

| Risk | Phase | Severity | Mitigation |
|---|---|---|---|
| pgvector not enabled on Railway Postgres plugin | 2 | M | One-line `CREATE EXTENSION vector;` via psql; verify in laptop-setup before migration. |
| MLX not portable to Railway | 2,3 | L | Ingestion is laptop-only by design. Output text/embeddings sync via outbox. |
| Decay half-life mismatched to operator intuition | 2 | M | Half-life is configurable per item; default `horizon/2` documented; revisit after 1 month of class-B usage. |
| Claude refusing to recommend "actions" in trading context | 3 | M | System prompt frames as "suggestions for operator review." Tool-use schema enforces structure. Test with real hypotheses early. |
| LLM hallucinating excerpt IDs | 3 | M | Validate every `evidence_excerpt_ids` entry against actual retrieved excerpts before persisting; drop unknowns. |
| Operator scope creep (more invalidator ops, more action kinds) | all | M | Lock the M-2 5-op DSL and 4 action kinds. New kinds = new ADR. |
| Cost overrun on Claude API | 3 | L | Daily token budget + per-query cap + cache. Solo operator ≪ enterprise traffic. |
| Embedding quality drift if BGE replaced later | 2 | L | Embedding column is single-table; re-embed cost = minutes for hundreds of items. |

## Estimated complexity

- **Phase 1 (M-2):** Medium. ~2-3 sessions. Backed by existing plan.
- **Phase 2 (Content layer):** Medium-High. ~3-4 sessions. New module, two ingestion paths, MLX setup, schema design.
- **Phase 3 (LLM stack):** High. ~4-5 sessions. Bundle assembly, prompt engineering, tool-use, approval flow, cost guardrails.
- **Total:** ~9-12 working sessions sequenced, plus operator-time for ingesting initial content corpus and authoring class-B horizons.

## Critical-path dependencies

```
Phase 1 (M-2)
   └─→ hypothesis table + status loop
         └─→ Phase 2 schema (content_hypothesis_links FK)
               └─→ Phase 2 ingestion + retrieval
                     └─→ Phase 3 bundle assembler
                           └─→ Phase 3 reasoning endpoint
                                 └─→ Phase 3 approval flow
```

Hard dependency at every arrow — no parallelism opportunity. Discipline = ship phase, run on it for ≥1 week, then start the next.

## Verification across all phases

End-to-end smoke after Phase 3 ships:
1. Ingest 1 class-A PDF (e.g. a Lyn Alden book chapter on liquidity) and link it to the BTC bottom thesis.
2. Ingest 1 class-B newsletter (latest weekly market commentary, horizon 3mo) and link it to the same thesis.
3. `POST /v1/research/ask` with query "is the BTC bottom thesis still tenable given this week's commentary?".
4. Receive verdict + evidence (mix of class-A and class-B excerpts, class-B weighted higher because fresh).
5. Receive `recommend_action` of `update_invalidator` kind (e.g. tighten DXY threshold).
6. Approve; confirm hypothesis row updated; confirm next lifespan tick re-evaluates.

If all six steps pass: the stack works end-to-end.

## Out of scope (explicitly deferred)

- Auto-extracting `horizon_months` from class-B content via LLM at ingestion time (M-4+).
- Multi-modal LLM (image charts in newsletters → reasoning) — defer until single-modal pipeline proves valuable.
- Multi-operator support — single-operator design throughout.
- Web UI for content ingestion — ingestion stays CLI; UI is for reading + linking.
- Telegram / push notifications when a hypothesis flips status due to new content — backlog.
- Backtest of LLM-action quality (M-6).

## Open questions — DEFERRED to Phase 2 + Phase 3 plan files

> **DO NOT resolve these now.** Operator decision (2026-05-01): brainstorm collaboratively when each phase enters its own planning session. Carry forward into the Phase-2 and Phase-3 dedicated plan files at promotion time.
> **Brainstorm-mode reminder:** when authoring those plan files, run a `/brainstorm` first — operator wants sparring on each, not a unilateral resolution.

### To carry into Phase 2 plan

1. **Embedding model** — BGE-small-en-v1.5 (384-dim, fast) is the default; reconsider against BGE-large (1024-dim, ~2× slower) once class-A corpus size is known.
2. **Class-A volume estimate** — rough count of PDFs/EPUBs over 6 months. Drives chunking constants and storage planning.
3. **Class-B sources** — specific newsletters / YouTube channels. Determines `author` taxonomy and informs scraping / yt-dlp testing.
4. **Operator ergonomics** — ingestion CLI on laptop primary vs minimal drag-drop UI. CLI is the default; revisit if friction shows up after a few ingests.

### To carry into Phase 3 plan

5. **Action kinds** — 4 proposed (`update_invalidator`, `cancel_hypothesis`, `create_opportunity`, `no_action`). Add / trim based on what operator actually wants the LLM to suggest.
6. **Bundle composition** — what state goes into the LLM bundle beyond the four currently planned (hypotheses, excerpts, macro, accuracy). E.g. recent trades? Recent opportunities? Open positions?
7. **Tool-use safety framing** — system prompt language to make Claude comfortable issuing `recommend_action` in a financial context. Test early with real hypotheses.
