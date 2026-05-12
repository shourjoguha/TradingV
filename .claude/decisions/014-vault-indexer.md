# ADR-014: Vault-indexer — substrate, storage, embedder, authoring discipline

**Date**: 2026-05-02
**Status**: Accepted (Phase 2 shipped)

## Context

After M-2 landed (hypothesis object), the next layer was an evidence
substrate — books, newsletters, videos the operator wants the platform to
reason over. Two reframes during the brainstorm:

1. **Substrate, not feature.** The operator wanted a personal-knowledge
   layer they would own (not just a TradingView content table). Future
   apps could read from it.
2. **Volume is small.** ~15 books + ~50 newsletters + ~50 videos per
   year ≈ 8M tokens. ~13k chunks at 600-tok each. Tiny by RAG standards.

Several decisions hung in the air. ADR captures the locked answers.

## Decisions

### 1. Substrate = an Obsidian vault on disk; indexer = a sidecar

Rejected: building a custom HTTP "knowledge service" with its own DB.

Accepted: vault at `~/Documents/knowledge-vault/`. A FastAPI sidecar
(`tools/vault_indexer/`) watches the vault, embeds notes, exposes HTTP.

**Reason:** the vault doubles as the operator's authoring UI for free
(Obsidian native). Source of truth stays in markdown — fully diffable in
git, recoverable from any backup, portable to any future consumer. The
sidecar's cache is rebuildable in <10 min; nothing of value lives there.

This sidesteps the "name the second consumer" challenge from the
brainstorm — Obsidian itself IS the first consumer of the substrate.
TradingView is the second.

### 2. Authoring discipline = B-mode (low-effort)

Rejected: A-mode wikilink discipline (the operator commits to authoring
`[[wikilinks]]` daily).

Accepted: tags + folders carry intent and hierarchy; embeddings carry
cross-connectivity; wikilinks are optional polish.

**Reason:** the operator was honest that they wouldn't sustain wikilink
discipline. Designing for occasional annotation matches reality. C-mode
("pure automation, never touch it") is the fallback if even occasional
review feels like a chore.

### 3. Storage = SQLite + sqlite-vec, not Postgres + pgvector

Rejected: pgvector on the existing TradingView Postgres.

Accepted: SQLite at `<vault>/.indexer/cache.db`, sqlite-vec virtual
table for KNN, `apsw` (not stdlib `sqlite3`) because Apple's Python
build disables loadable extensions.

**Reason (drove the decision at execution time):** the laptop's
`tradingview-laptop-pg` docker image doesn't ship pgvector — `CREATE
EXTENSION vector` fails. Three options were considered: swap docker
image (risk + churn), install extension into running container
(brittle), or move to SQLite. SQLite wins because the indexer becomes
self-contained (single file cache), volume is small enough that
sqlite-vec performs adequately, and decoupling from TradingView's pg is
desirable anyway for portability.

### 4. Embedder = `BAAI/bge-large-en-v1.5` (1024-d, cosine-native)

Rejected:
- `all-MiniLM-L6-v2` (384-d, MTEB ~42) — too conservative; ~20pp recall
  gap vs bge-large at our scale is real, not academic.
- `multi-qa-mpnet-base-dot-v1` (768-d, MTEB ~52) — better than MiniLM,
  asymmetric Q→passage specialization, but trained for dot product on
  un-normalized vectors which forces a normalize-at-encode trick to fit
  sqlite-vec's cosine KNN.

Accepted: bge-large. Higher MTEB retrieval (~64), cosine-native (clean
sqlite-vec fit), already cached locally (~1.3 GB sitting on disk
otherwise idle), newer training corpus (handles contemporary
newsletter/video terminology better).

**Reason:** at solo-operator volume, query-time cost differences across
model sizes are zero (a few queries/day). The thing that matters is
which excerpts come back when the operator asks "what's at risk in my
BTC bottom thesis?" — better-trained model wins that lottery more
often. Schema set to `FLOAT[1024]`. Query-side prefix
`"Represent this sentence for searching relevant passages: "` per bge
guidance; passages encoded raw.

mpnet documented as the explicit fallback if bge misbehaves
(normalize-at-encode + schema swap to `FLOAT[768]`).

### 5. Decay = `exp(-age_months / (horizon/2))` for class B

Class A (`book`, `book_chapter`, `note`, `topic`) → weight = 1.0.
Class B (`newsletter`, `video`, or any timely-folder note) →
exponential decay. Half-life = horizon / 2.

**Reason:** newsletters and videos make claims valid over a stated
horizon. After half that horizon, the claim is half as relevant.
Operator can override per-note (`horizon_months: null` makes a class-B
note timeless). Storage-side does no decay; the weight is applied at
retrieval time, so changing the formula doesn't require re-embedding.

### 6. Tags from a small controlled vocabulary, hand-edited

Vocabulary lives in `<vault>/_taxonomy.md` with 15 starter tags. Operator
edits the file directly:
- Add: new bullet line.
- Edit description: rewrite the text after the dash.
- Remove: delete the bullet — orphans flagged in review queue.
- Rename: add `old → new` to RENAMES block; indexer rewrites every
  note's frontmatter atomically and strips the directive.

**Reason:** free-form tags fragment fast (`liquidity` vs `Liquidity` vs
`monetary`). A small vocabulary keeps retrieval connected and the auto-
tag prompt focused. Hand-editing the file in Obsidian is more
ergonomic than CRUD endpoints. RENAMES-block + auto-rewrite is the
operator's escape hatch for vocabulary evolution.

### 7. Operator review = markdown checkboxes, no separate UI

Indexer regenerates `_review-queue.md` periodically. Operator ticks
checkboxes in Obsidian, saves. Next watch event reads the ticks and
applies them.

**Reason:** the cheapest possible operator-in-the-loop. Zero new UI to
build. Pure markdown ergonomics. If review-tick discipline lapses for
weeks, the queue regenerates with the same suggestions — no lost work.
Long-term escape hatch: flip `AUTO_PROMOTE_THRESHOLD` config to
auto-apply suggestions above a similarity bar (off by default).

### 8. Auto-tag with Claude Haiku, vocabulary-constrained

`claude-haiku-4-5` proposes 1–5 tags from `_taxonomy.md` per ingested
note. Suggestions go to the review queue; operator approves.

**Reason:** the cheap classifier model is enough at vocabulary-
constrained classification. ~$0.20/yr at expected volume. Off when
`ANTHROPIC_API_KEY` is missing — indexer never writes a tag the
operator didn't tick.

### 9. Indexer lives at `tools/vault_indexer/` in TradingView repo

Same repo until a second consumer materializes. Extract to its own repo
when the second consumer ships — `git mv` + a release tag.

**Reason:** monorepo today, decoupling tomorrow. The indexer has zero
runtime dependency on TradingView; only the test suite shares pytest +
fixtures. Easy to peel off.

## Consequences

- ~1100 lines of new code (~700 indexer + ~400 ingestion). One TradingView
  migration (0022). 9 new tests, full suite 323 green.
- `apsw` and `sentence-transformers` installed in TradingView's venv —
  shared, no second venv. (Risk noted: if dependency clash, indexer can
  move to its own venv with one config change.)
- `pgvector` cleanup avoided. The boot-vs-alembic race triggered the
  same `create_all` wart we filed in [backlog.md](../status/backlog.md);
  manual cleanup applied as before. **Backlog item resolved 2026-05-02
  immediately after Phase 2 ship** — `Base.metadata.create_all` removed
  from lifespan; replaced with `app/core/schema_check.py` that logs a
  loud WARN on revision drift. Tests-only `create_all` lives in
  `tests/conftest.py`. No more silent table auto-creation.
- Operator owes a few minutes / week of review-queue tick discipline.
  If they don't, no harm — the queue regenerates harmlessly.

## Alternatives considered

- **Custom standalone knowledge service with its own DB and graph
  schema.** Rejected — heavy build, no second consumer to justify it
  yet, vault-as-substrate gets 80% of the value with 20% of the code.
- **Wikilinks as primary connectivity (A-mode).** Rejected — operator
  honest about discipline; B-mode is realistic.
- **NotebookLM as the substrate.** Rejected during brainstorm — closed
  silo, no clean API, can't tie into hypothesis-link layer.
- **Compress class-B content at ingest** ("the same expert weekly").
  Rejected — solving a problem we don't have at this volume; storage
  isn't the constraint, retrieval quality is, and that's a retrieval-
  side fix (auto-summarize on demand) not a storage-side fix.
- **MLX embeddings.** Considered, fell back to sentence-transformers
  because torch is already installed (Kronos brings it). MLX would have
  added install friction for marginal speed gain.
- **Postgres + pgvector.** Considered, rejected after `CREATE EXTENSION
  vector` failed on the laptop pg image. SQLite + sqlite-vec turned out
  to be a better architectural choice anyway.

## Footer — re-evaluated 2026-05-02 against LightRAG + Gemini embeddings

Operator-prompted comparison ([`plans/i-want-to-compare-declarative-kazoo.md`](../plans/i-want-to-compare-declarative-kazoo.md)).
**No change.** `bge-large-en-v1.5` stays for the text-modality path.

- **LightRAG**: solves multi-hop / cross-source queries, not the
  single-thesis stress-test the Phase 3 use case demands. Switching now
  pays graph-maintenance cost without using it. Parked behind a
  separate trigger (first single-source-retrieval failure where
  entity-aware filtering would have helped) as the
  [LightRAG-lite backlog item](../status/backlog.md). The backlog steal
  is entity-extraction-into-frontmatter — ~70% of the entity-aware
  win at ~5% of the cost.
- **Gemini text embeddings** (`gemini-embedding-001` /
  `text-embedding-005`): ~3 MTEB points over bge-large for 5-30× the
  latency, full network dependency, and content-leaves-the-laptop on
  every embed. Marginal gain isn't worth the trade-offs at solo-operator
  volume.
- **Gemini multimodal embeddings** (`multimodalembedding@001`): the one
  genuinely interesting option. Doesn't replace the text path; it
  unlocks an image-modality path that doesn't yet exist. Parked behind
  the existing
  [vision-retrieval backlog item](../status/backlog.md)'s 3-concrete-moments
  trigger, with Gemini-vs-local-CLIP/SigLIP as the candidate-stack
  question to resolve at trigger time.

The single principle binding all three: don't change a working stack to
serve queries that haven't been asked.
