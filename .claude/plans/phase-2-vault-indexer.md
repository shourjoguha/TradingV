# Phase 2 — Knowledge vault + indexer sidecar

> **Status: SHIPPED 2026-05-02.** See [.claude/vault.md](../vault.md) and [decisions/014](../decisions/014-vault-indexer.md) for the as-built. This plan file is kept as the as-planned record.
> Supersedes the Phase-2 stub in [`M-2-then-content-then-llm.md`](M-2-then-content-then-llm.md).
> Brainstorm converged on Obsidian-vault-as-substrate (B-mode: low-discipline authoring; embeddings carry connectivity; tags from a controlled vocabulary carry intent; folders carry hierarchy).

## Context

M-2 shipped 2026-05-01 — the platform now has structured beliefs (hypotheses) but no evidence layer. Phase 2 builds the evidence substrate: a personal knowledge layer the operator authors (occasionally) and machines populate (mostly via n8n) — both feeding TradingView's eventual `/research/ask` endpoint and any future apps that need the same substrate.

Vault already exists at `~/Documents/knowledge-vault/`:

```
.obsidian/                    -- real Obsidian config
Books/
Newsletters/
Notes/
Topics/
Videos/
Welcome.md                    -- delete or ignore
_review-queue.md              -- empty; indexer will populate
_taxonomy.md                  -- empty; indexer seeds, operator hand-edits
```

## Locked decisions (from brainstorm)

1. **Source of truth = the vault.** Markdown on disk. SQLite cache in indexer is rebuildable; if it disappears, no data is lost.
2. **B-mode authoring.** Operator writes occasionally, not on cadence. Embeddings carry cross-connectivity; tags carry operator intent; folders carry hierarchy. Wikilinks are optional polish.
3. **Controlled tag vocabulary.** ~15–25 tags lived in `_taxonomy.md`. Operator hand-edits the file (add / edit description / remove / rename). Indexer reloads on file change.
4. **Auto-tag with vocabulary constraint.** At ingest, an LLM proposes 3–5 tags from `_taxonomy.md` only. Operator approves via the weekly review file.
5. **Weekly review queue is markdown.** Indexer rewrites `_review-queue.md` every 7 days. Operator ticks checkboxes in Obsidian. Indexer reads back ticks on next watch event and promotes them.
6. **Decay on retrieval.** Class B (Newsletters/Videos) carries `horizon_months` in frontmatter; indexer applies `exp(-age/(horizon/2))` weighting at search time. Class A (Books/Notes/Topics) is timeless, weight = 1.0.
7. **Indexer is local.** Runs on the laptop alongside the existing TradingView API. **SQLite + sqlite-vec** for the cache (self-contained file at `<vault>/.indexer/cache.db` — decouples indexer from TradingView's pg, which doesn't ship pgvector in its current image).
8. **Embedder = sentence-transformers + `BAAI/bge-large-en-v1.5`.** 1024-dim, ~1.3 GB, **already cached** at `~/.cache/huggingface/hub/models--BAAI--bge-large-en-v1.5/`. Highest MTEB retrieval of the three cached models (~64 vs mpnet ~52 vs MiniLM ~42); cosine-native (clean sqlite-vec fit); newer training corpus handles contemporary newsletter terminology better. Query-side requires the recommended prefix `"Represent this sentence for searching relevant passages: <query>"`; passages encoded raw. Reuses the existing torch 2.11.0 in TradingView's venv.
9. **Transcription = `openai-whisper` + `whisper-small`** — fresh install (~50 MB lib + 470 MB weights). Reuses torch.

## Goals (Phase 2 exit criteria)

- 3 books + 3 newsletters + 3 videos ingested into the vault as markdown.
- Each ingested note carries valid frontmatter (`kind`, `published_at`, `horizon_months` for class B, `tags`).
- `_taxonomy.md` seeded with 15 starter tags; operator-edits round-trip cleanly (add / edit / remove / rename all handled).
- `_review-queue.md` regenerates weekly with auto-tag + auto-link suggestions; operator can promote suggestions by ticking checkboxes in Obsidian.
- Indexer exposes `GET /search?q=&k=`, `GET /traverse/{path}?depth=N`, `GET /node/{path}` over HTTP.
- `hypothesis_node_links` table on TradingView side stores per-hypothesis pointers to vault paths.
- End-to-end smoke: `curl /search?q=stagflation` returns ranked excerpts from at least 2 different vault folders, decay-weighted appropriately.

## Architecture

```
~/Documents/knowledge-vault/  (Obsidian vault — operator's personal space)
            ▲
            │ writes markdown
            │
   ┌────────┴──────────┐                          ┌──────────────────┐
   │ Ingestion workers │ ◄─── n8n triggers ─────  │ External:        │
   │ (laptop, MLX):    │                          │ newsletter feeds │
   │   pdf/epub→md     │                          │ video uploads    │
   │   yt-dlp→whisper  │                          └──────────────────┘
   │   readability→md  │
   └───────────────────┘

            ▼ writes
   ┌──────────────────────────────────────┐
   │  vault-indexer  (FastAPI sidecar)    │   ← watches vault for changes
   │  port 8001                            │   ← embeds via MLX BGE-small
   │                                       │   ← caches in Postgres
   │  GET  /search?q=&k=                   │   ← regenerates _review-queue.md
   │  GET  /traverse/{path}?depth=N        │     weekly
   │  GET  /node/{path}                    │
   │  POST /reload    (force vault rescan) │
   │  POST /promote   (apply review ticks) │
   └──────────────────────────────────────┘
            ▲
            │ HTTP (no auth — laptop-local)
            │
   ┌────────┴──────────┐
   │ TradingView API   │   ← future: /v1/research/ask consumes via indexer
   │ (port 8000)       │
   └───────────────────┘
```

Indexer code lives at `tools/vault-indexer/` in the TradingView repo for v1 — it's small enough that a separate repo is overhead. **Extract to its own repo only when a second consumer materializes**; the move is one `git mv`.

## Vault frontmatter schema

Every markdown note ingested by a worker carries YAML frontmatter. Hand-authored notes are encouraged to too but indexer tolerates missing fields.

```yaml
---
kind: book | book_chapter | newsletter | video | note | topic
title: "..."
author: "..."                  # for class B; optional for Notes
source_url: "..."              # nullable for hand-authored notes
published_at: 2026-05-15       # date the content was created
ingested_at: 2026-05-15T18:00Z # when this file was created in the vault
horizon_months: 6              # class B only; null/missing → 6mo default for class B
parent: "Books/lyn-alden-broken-money/index.md"  # optional; for chapter→book
tags: [liquidity, dollar_cycle]
---

# Body markdown follows.
```

**Decay weight at retrieval:**
- `kind ∈ {book, book_chapter, note, topic}` → weight = 1.0 (timeless)
- `kind ∈ {newsletter, video}`, `horizon_months = H` → `weight = exp(-age_months / (H/2))`
- Operator can override by setting `horizon_months: null` on a class-B note to mark it as timeless (e.g. a foundational essay even though delivered as a newsletter).

## `_taxonomy.md` format

Operator-editable. Indexer reloads on file change.

```markdown
# Vault tag vocabulary

Edit this file freely. Indexer reloads on save. To rename a tag, see "RENAMES" block at bottom.

## Active tags

- `liquidity` — central bank balance sheet, money market plumbing, repo
- `growth_vs_inflation` — copper/gold, breakevens, real yields
- `regime_shift` — multi-year change in macro regime (stagflation, debasement, etc.)
- `monetary_policy` — Fed/ECB/BoJ rate decisions, forward guidance
- `energy` — oil, gas, electricity demand, energy transition
- `em_breakout` — emerging-markets ratios, USD-EM dynamics
- `btc` — Bitcoin-specific (price action, on-chain, MSTR)
- `software_durability` — SaaS pricing power vs AI commoditization
- `single_name_conviction` — high-conviction picks (PATH, OKTA, etc.)
- `technical_breakout` — chart-pattern-driven theses
- `dollar_cycle` — DXY, USD strength/weakness regime
- `credit_cycle` — HY/IG spreads, default cycle
- `valuations` — multiples, mean reversion arguments
- `sentiment` — survey data, fund-flow indicators
- `geopolitics` — war, sanctions, trade policy

## RENAMES (one-shot; remove lines after indexer applies)

# old_name → new_name
```

Operator edits:
- **Add a tag:** new line under "Active tags." Indexer picks it up on next watch event; future auto-tag suggestions can use it.
- **Edit description:** rewrite the right-hand side. Affects the auto-tag prompt context only; existing tagged notes unchanged.
- **Remove a tag:** delete its line. Notes that already use it retain the tag in their frontmatter; indexer flags them in `_review-queue.md` as "uses removed tag — re-tag or accept as deprecated."
- **Rename a tag:** add a line under "RENAMES" (e.g. `inflation → growth_vs_inflation`). On next watch event, indexer rewrites every note's frontmatter to apply the rename, removes the line, logs the rewrites in `_review-queue.md`. Atomic per-tag.

## `_review-queue.md` lifecycle

Indexer rewrites this file weekly (Sunday 09:00 local) AND on-demand via `POST /reload`. Operator opens it in Obsidian, ticks boxes, saves. Indexer's next watch event reads ticks, promotes them, then regenerates the file with the next batch.

```markdown
# Review queue — week of 2026-05-15

Tick boxes to promote. Indexer applies on next save.

## Auto-tag suggestions

### Newsletters/lyn-alden/2026-w19.md
- [ ] tag: `liquidity`
- [ ] tag: `dollar_cycle`
- [ ] tag: `regime_shift`

### Videos/raoul-pal/2026-05-12.md
- [ ] tag: `btc`
- [ ] tag: `valuations`

## Cross-link suggestions (similarity > 0.78)

### Newsletters/lyn-alden/2026-w19.md
- [ ] link → Books/lyn-alden-broken-money/ch-04.md (sim 0.84)
- [ ] link → Newsletters/lyn-alden/2026-w17.md (sim 0.81)

## Hypothesis link suggestions

### stagflation-regime-24m
- [ ] supports → Newsletters/lyn-alden/2026-w19.md
- [ ] context → Books/lyn-alden-broken-money/ch-04.md

### btc-bottom-3m
- [ ] challenges → Videos/raoul-pal/2026-05-12.md

## Vocabulary candidates

These free-form tags appeared in your hand-tagged notes but aren't in `_taxonomy.md`:
- [ ] promote `recession_2024` to vocabulary (3 uses)

## Orphaned tags (in notes but no longer in vocabulary)

- `inflation` — used in 4 notes. Re-tag with one of: growth_vs_inflation, regime_shift, monetary_policy, OR accept as deprecated.
```

## Components

### 1. Indexer sidecar — `tools/vault-indexer/`

Files (all new):
- `app.py` — FastAPI wiring + lifespan
- `vault.py` — vault scanner + frontmatter parser + watcher (`watchdog`)
- `taxonomy.py` — `_taxonomy.md` parse + RENAMES handling
- `review.py` — `_review-queue.md` generator + tick-reader
- `embed.py` — `sentence-transformers` loading `BAAI/bge-large-en-v1.5` from the existing HF cache. Query encoder applies the bge-recommended prefix; passage encoder runs raw.
- `index.py` — SQLite + sqlite-vec cache (DB file at `<vault>/.indexer/cache.db`)
- `routes.py` — search / traverse / node / reload / promote endpoints
- `decay.py` — exponential weighting per kind
- `auto_tag.py` — Claude API call to suggest tags from vocabulary
- `pyproject.toml` + `requirements.txt` — own deps, no TradingView dep
- `README.md`

Boots on port 8001 alongside the TradingView API. Configurable via env:
```
VAULT_PATH=/Users/shourjosmac/Documents/knowledge-vault
INDEXER_DB_PATH=/Users/shourjosmac/Documents/knowledge-vault/.indexer/cache.db
ANTHROPIC_API_KEY=...
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5                       # cached locally
WHISPER_MODEL=small                                          # fresh install
```

### 2. Indexer DB schema (SQLite + sqlite-vec; cache only, vault is canonical)

```sql
CREATE TABLE vault_node (
  path TEXT PRIMARY KEY,        -- e.g. "Newsletters/lyn-alden/2026-w19.md"
  kind TEXT NOT NULL,
  title TEXT,
  author TEXT,
  published_at TEXT,            -- ISO yyyy-mm-dd
  ingested_at TEXT,             -- ISO timestamp
  horizon_months INTEGER,       -- nullable
  parent_path TEXT,             -- nullable
  tags TEXT NOT NULL DEFAULT '[]',  -- JSON array (sqlite has no native array)
  body_hash TEXT NOT NULL,      -- detect changes (xxhash or sha256)
  body_md TEXT NOT NULL,
  last_indexed_at TEXT NOT NULL
);

CREATE TABLE vault_chunk (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL REFERENCES vault_node(path) ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  text TEXT NOT NULL,
  section TEXT,
  UNIQUE (path, ord)
);

-- sqlite-vec virtual table; rowid joins to vault_chunk.id
CREATE VIRTUAL TABLE vault_chunk_vec USING vec0(
  chunk_id INTEGER PRIMARY KEY,
  embedding FLOAT[1024]
);

CREATE TABLE vault_edge (
  src_path TEXT NOT NULL,
  dst_path TEXT NOT NULL,
  kind TEXT NOT NULL,           -- 'parent' | 'wikilink' | 'auto_similar'
  weight REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (src_path, dst_path, kind)
);
```

**Why SQLite + sqlite-vec instead of Postgres + pgvector:** the laptop's running pg image (`tradingview-laptop-pg`) doesn't ship pgvector — `CREATE EXTENSION vector` fails. Three options were considered: swap the docker image, install the extension into the running container, or use SQLite. SQLite wins because (a) it makes the indexer self-contained and portable to any future consumer without a pg dependency, (b) volume is small (~13k chunks/yr — sqlite handles this comfortably), (c) zero extension-install friction. Trade-off: single-writer (fine — indexer is the only writer).

DB lives at `<VAULT_PATH>/.indexer/cache.db`. Wipe + rebuild in <10 min if anything goes sideways. Fully derivable from the vault.

### 3. Ingestion workers — `tools/vault-indexer/ingest/`

CLI scripts. Each writes markdown into the appropriate vault folder, then optionally hits `POST /reload` so the indexer picks up immediately (otherwise watcher catches it within ~2 seconds).

- `ingest_pdf.py --path=<file> --kind=book` — PyMuPDF extract → split by `# heading` boundaries → one note per chapter under `Books/<slug>/`. Auto-creates an index note linking the chapters.
- `ingest_epub.py --path=<file>` — same shape via `ebooklib`.
- `ingest_video.py --url=<youtube> --author=<slug> --horizon=6` — yt-dlp audio → MLX-Whisper → markdown into `Videos/<author>/<yyyy-Www>.md`.
- `ingest_newsletter.py --url=<url> --author=<slug> --horizon=3` — `readability-lxml` extract → markdown into `Newsletters/<author>/<yyyy-Www>.md`. Or `--text-file=<path>` for paste.

n8n calls these via SSH or local webhook (n8n itself can run anywhere; a small FastAPI endpoint on the laptop accepts trigger payloads and runs the script).

### 4. Auto-tag flow

Triggered when indexer ingests a new note (kind in `newsletter` / `video`, optionally `note`). One Claude API call per note (~$0.001/call with Haiku):

```
SYSTEM: You tag a markdown note with the operator's controlled vocabulary.
Pick the 1-5 most-applicable tags. Use ONLY the listed tags. If no tag
fits, return an empty list. Never invent new tags.

VOCABULARY:
{rendered active-tags block}

NOTE:
{note body, truncated to 4k tokens}

OUTPUT JSON: {"tags": ["..."], "reasoning": "..."}
```

Suggestions go to `_review-queue.md` as checkboxes. Operator approves; indexer rewrites the note's frontmatter `tags:` list with the approved set.

### 5. TradingView integration (deferred to Phase 3, schema lands here)

```sql
CREATE TABLE hypothesis_node_links (
  hypothesis_id UUID NOT NULL REFERENCES hypothesis(id) ON DELETE CASCADE,
  vault_path TEXT NOT NULL,     -- e.g. "Newsletters/lyn-alden/2026-w19.md"
  stance TEXT NOT NULL CHECK (stance IN ('supports','challenges','context')),
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  added_by TEXT NOT NULL CHECK (added_by IN ('operator','auto')),
  PRIMARY KEY (hypothesis_id, vault_path)
);
```

This is on TradingView side, not in the indexer. TradingView calls the indexer over HTTP for retrieval but joins to its own table for stance + hypothesis context. Migration `0022_hypothesis_node_links.py`.

## Plan summary

| # | Task | Effort | Notes |
|---|---|---|---|
| 1 | Seed `_taxonomy.md` with 15 starter tags + RENAMES section | 5 min | Operator can edit immediately. |
| 2 | Scaffold `tools/vault-indexer/` (FastAPI app, deps, README) | 30 min | Empty endpoints. |
| 3 | Vault scanner + frontmatter parser + SQLite cache (sqlite-vec virtual table) | 2 hrs | `pip install sqlite-vec watchdog python-frontmatter`. |
| 4 | Embedder via `sentence-transformers` loading cached `BAAI/bge-large-en-v1.5` | 1 hr | `pip install sentence-transformers`. Reuses torch 2.11 in venv. Zero model download (already cached). Apply bge query prefix on query path; passages encoded raw. |
| 5 | `/search`, `/node`, `/traverse` endpoints | 2 hrs | Decay applied at search time. |
| 6 | Taxonomy parser + RENAMES handler | 1 hr | Atomic per-tag rewrites. |
| 7 | Auto-tag (Claude Haiku) | 1 hr | ~$0.20/yr at expected volume. |
| 8 | Review queue generator + tick-reader | 2 hrs | Markdown round-trip; idempotent. |
| 9 | Ingestion workers (4 scripts) | 3 hrs | `pip install pymupdf ebooklib readability-lxml yt-dlp openai-whisper`. Whisper-small weights ~470 MB on first run. |
| 10 | TradingView migration `0022_hypothesis_node_links` | 30 min | Just the table; routes are Phase 3. |
| 11 | UAT smoke (3 books + 3 newsletters + 3 videos end-to-end) | 1 hr | See Verification below. |
| **Total** | | **~14 hrs** | ~2-3 focused sessions. |

### Pre-flight (already done 2026-05-02)

- HF cache inspected at `~/.cache/huggingface/hub/`. Three already-cached options were compared:
  - `models--BAAI--bge-large-en-v1.5` ✓ (1024-d, ~1.3 GB, MTEB retrieval ~64) — **chosen**
  - `models--sentence-transformers--multi-qa-mpnet-base-dot-v1` ✓ (768-d, MTEB ~52) — second-best; specialized for asymmetric Q→passage but trained for dot-product geometry, requires normalize-at-encode trick to fit sqlite-vec's cosine KNN. Fallback if bge gives any trouble.
  - `models--sentence-transformers--all-MiniLM-L6-v2` ✓ (384-d, MTEB ~42) — rejected as too conservative; quality gap vs bge-large is real (>20 pp).
  - **No** Whisper weights cached — first transcription will fetch `whisper-small` (~470 MB).
- TradingView venv: only `torch 2.11.0` present. All other deps in steps 3/4/9 are fresh installs.
- pgvector on `tradingview-laptop-pg`: **not available** — drove the SQLite + sqlite-vec decision.
- New disk footprint estimate: ~525 MB on first ingest run (whisper-small + indexer deps; bge-large is already cached, so zero embedding-model download).

## Open questions (do NOT resolve now — operator may decide as we go)

1. **Indexer location** — `tools/vault-indexer/` in TradingView repo (recommended) vs separate repo from day 1. Recommendation: same repo until a second consumer materializes; extract is `git mv`.
2. **Auto-tag model** — Claude Haiku (cheap, fast, fine for vocabulary-constrained classification) vs Sonnet (better quality, ~10× cost). Recommendation: Haiku.
3. **Auto-promote threshold** — if operator skips review for >2 weeks, indexer can auto-promote suggestions above similarity 0.85. Off by default; flag in config.
4. **Obsidian Smart Connections plugin** — optional UI complement that surfaces similarity inline in Obsidian. Not required (the indexer + review queue cover the same ground), but the operator may enjoy it. Defer until vault is populated.
5. **Embedding model** — chosen `BAAI/bge-large-en-v1.5` at v1 (cached, MTEB ~64, cosine-native). If retrieval quality disappoints OR encoding speed becomes an issue at scale, swap to `multi-qa-mpnet-base-dot-v1` (also cached, asymmetric-specialized) — schema swap to `FLOAT[768]` + add `normalize_embeddings=True` at encode.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| ~~pgvector not on laptop pg~~ | — | Resolved at design time — switched to SQLite + sqlite-vec. |
| sentence-transformers conflicts with TradingView's torch 2.11 | L | sentence-transformers pins are loose; should resolve. If clash: pin sentence-transformers in `tools/vault-indexer/requirements.txt` independently and run indexer in its own venv. |
| Whisper-small download (~470 MB) on first ingest | L | Operator-aware; pre-warm by running `whisper.load_model('small')` once during step 9 install. |
| Watchdog misses file changes during high-write bursts | L | `POST /reload` is the manual fallback; cron 1-hourly safety rescan. |
| Operator edits `_taxonomy.md` mid-rename batch | M | Indexer locks the file during a rename pass; rare given solo operator. |
| Auto-tag LLM proposes the wrong tag often | M | Operator can flip to "no auto-tag, review-queue only" via env flag. Tag accuracy improves as vocabulary stabilizes. |
| Vault-indexer drift from vault | L | Cache is fully rebuildable from vault. Nuke `<vault>/.indexer/cache.db` and re-embed in <10 min at 13k chunks. |

## Verification (UAT — what "Phase 2 ships" means)

Run in order, all must pass:

1. `_taxonomy.md` seeded; manually add a tag → indexer reloads → next auto-tag suggestion can use it.
2. `_taxonomy.md` rename-block applied → all notes' frontmatter rewritten → rename-line removed → log entry in `_review-queue.md`.
3. Drop a PDF via `python tools/vault-indexer/ingest/ingest_pdf.py --path=...` → `Books/<slug>/` populated → indexer embeds → `GET /search?q=...` returns chunks from it.
4. Run `ingest_video.py` against a real YouTube URL → transcript markdown lands in `Videos/...` → auto-tag fires → suggestions appear in `_review-queue.md`.
5. Tick boxes in `_review-queue.md` for tags + cross-links → save → indexer applies → frontmatter updated → next regeneration omits the applied items.
6. Edit a note's `horizon_months` → next `/search` ranks it differently per decay weight.
7. `GET /traverse/Books/lyn-alden-broken-money/index.md?depth=2` returns the chapter notes plus their first-degree similar notes.
8. Apply migration `0022_hypothesis_node_links` on the TradingView DB → table exists, no regressions in 314 existing tests.

## Out of scope (Phase 3+)

- TradingView's `/v1/research/ask` endpoint (bundle assembler + Claude tool-use). Phase 3.
- Operator UI for managing the review queue beyond plain markdown checkboxes.
- Multi-vault support.
- Telegram notification when the review queue regenerates.
- Auto-promote at high confidence (kept as off-by-default config flag).
- Wikilink-graph parsing — indexer ignores `[[wikilinks]]` in v1 (operator B-mode doesn't author them); add later if operator changes their authoring habit.
- Obsidian plugin authoring. The vault works with vanilla Obsidian.

## Critical files (paths)

**New under TradingView repo:**
- `tools/vault-indexer/{app,vault,taxonomy,review,embed,index,routes,decay,auto_tag}.py`
- `tools/vault-indexer/ingest/{ingest_pdf,ingest_epub,ingest_video,ingest_newsletter}.py`
- `tools/vault-indexer/{requirements.txt,pyproject.toml,README.md}`
- `migrations/versions/0022_hypothesis_node_links.py`
- `tests/test_vault_indexer.py` (separate from main suite; mocks vault dir)

**Edits in TradingView repo:**
- `app/main.py` — register the `Hypothesis_node_link` model for `create_all` test parity (deferred until Phase 3 ROUTES — schema-only for Phase 2).
- `tests/conftest.py` — same registration.
- `.claude/hypotheses.md` — add a "linked content" section once Phase 3 lands; no edit this phase.

**Vault (operator's machine, NOT in repo):**
- `~/Documents/knowledge-vault/_taxonomy.md` — seeded by indexer one-shot, hand-edited thereafter.
- `~/Documents/knowledge-vault/_review-queue.md` — fully indexer-managed.
- `~/Documents/knowledge-vault/{Books,Newsletters,Videos,Notes,Topics}/` — populated by ingestion workers + operator.

## Sequencing within Phase 2

Two checkpoints inside the phase, in case anything wobbles:

**Checkpoint A (after step 5):** end-to-end one-note flow. Manually drop a single markdown file in `Notes/`, watch indexer ingest it, embed it, return it via `/search`. Verifies the spine before adding ingestion + auto-tag complexity.

**Checkpoint B (after step 9):** all four ingestion paths exercised. Three real items per kind. Stop here if anything feels wrong before wiring TradingView.

Phase 2 ships at step 11.
