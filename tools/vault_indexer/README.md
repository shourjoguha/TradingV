# vault-indexer

Personal-knowledge sidecar for the operator's Obsidian vault. Watches a
markdown vault, embeds notes with `BAAI/bge-large-en-v1.5`, caches in
SQLite + sqlite-vec, and serves an HTTP API that TradingView (and any
future app) can read.

Phase 2 of the macro-workbench → decision-tool roadmap. Source of truth =
the vault on disk; the cache is fully rebuildable in <10 min.

## Run

```bash
cd /Users/shourjosmac/Documents/Claude/TradingView
source venv/bin/activate
export VAULT_PATH=$HOME/Documents/knowledge-vault
uvicorn tools.vault_indexer.app:app --port 8001 --reload
```

Env vars (all optional except as noted):

| Var | Default | Notes |
|---|---|---|
| `VAULT_PATH` | `~/Documents/knowledge-vault` | Required to exist at boot. |
| `INDEXER_DB_PATH` | `<VAULT_PATH>/.indexer/cache.db` | Created on first run. Convention: set explicitly to `cache-<domain>.db` on multi-domain installs. The launchd plists for finance/fitness/nutrition all set this. |
| `DOMAIN` | _(unset)_ | Slug from `<VAULT_PATH>/_domains.yaml` registry. Drives include/exclude scope. Single-vault legacy installs may omit. |
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` | Must be in HF cache. |
| `EMBEDDING_DIM` | `1024` | Match the schema; if you swap models, update this and re-init the cache. |
| `BGE_QUERY_PREFIX` | `Represent this sentence for searching relevant passages: ` | bge-recommended. |
| `ANTHROPIC_API_KEY` | _(empty)_ | Auto-tag silently disabled when missing. |
| `AUTO_TAG_MODEL` | `claude-haiku-4-5` | |
| `AUTO_TAG_ENABLED` | `1` | Set `0` to skip Claude calls entirely. |
| `DEFAULT_HORIZON_MONTHS` | `6` | Used when class-B note has no `horizon_months` in frontmatter. |
| `TIMELY_FOLDERS` | `Newsletters,Videos` | Comma-separated. |
| `CHUNK_TARGET_TOKENS` | `600` | Word-approx; chunks up sections longer than this. |
| `CHUNK_OVERLAP_TOKENS` | `80` | |
| `DECAY_MODE` | yaml-derived | `ranked_grouped` (finance) or `off` (fitness/nutrition). Override per `<vault>/_domains.yaml`. |
| `DECAY_LADDER` | `1.0,0.6,0.45,0.35,0.25` | Per-rank weights when mode=ranked_grouped. Same-author content ranked by `published_at` desc. |
| `DECAY_FLOOR` | last rung of ladder | Weight applied when rank ≥ len(ladder). |
| `DECAY_GROUP_KEY` | `author` | Field used to group competing content. `author` covers Newsletters/Videos; Filings have no author and stay ungrouped (no penalty). |
| `DECAY_EVERGREEN_PATHS` | yaml-derived | Comma-separated glob patterns. Paths matching get weight=1.0 regardless of rank. Finance: `Books/**`. fitness/nutrition: `**`. |
| `LEXICAL_ENABLED` | yaml-derived | `1` to fuse FTS5 lexical signal into retrieval via RRF. Default on for all domains. |
| `LEXICAL_VECTOR_WEIGHT` | `1.0` | RRF weight for the vector leg. |
| `LEXICAL_LEXICAL_WEIGHT` | `0.5` (finance) / `0.05` (fitness, nutrition) | RRF weight for the lexical leg. Lower = vector dominates. |
| `LEXICAL_MIN_TOKENS` | `2` | Skip the lexical leg when sanitized query has fewer tokens (single-word queries are too noisy). |

## Endpoints

| | |
|---|---|
| `GET /health` | Sanity probe. |
| `POST /reload` | Apply pending RENAMES + full vault rescan + regenerate review queue. |
| `GET /node/{path:path}` | Raw node row (frontmatter + body). |
| `GET /search?q=&k=&excerpts=&parse=` | Hybrid retrieval: query parser → metadata pre-filter → vector KNN + lexical FTS5 → RRF merge → ranked-grouped decay → graph hybrid re-rank. Response includes `parsed: {tickers, kinds, since, raw_terms, has_anchors}` and per-result `decay_rank`, `decay_weight`, `rrf_score`, `rank_vector`, `rank_lexical`, `lexical_score` when applicable. Pass `parse=false` to bypass anchor extraction; `excerpts=false` to skip the (slow) per-chunk extractive teaser. |
| `GET /traverse/{path:path}?depth=N` | Local subgraph (explicit edges + similarity). |
| `POST /promote` | Read ticks from `_review-queue.md` AND scan `Research/*.md` for ticked Approve/Dismiss boxes; apply both; regenerate the queue. |
| `POST /apply-renames` | Manual trigger for the RENAMES block in `_taxonomy.md`. |
| `POST /regenerate-review` | Force a fresh review queue without ingesting anything. |

## Vault layout (operator-managed)

```
~/Documents/knowledge-vault/
  .obsidian/
  Books/<book-slug>/index.md, ch-01.md, ...
  Newsletters/<author>/2026-w19-...md
  Videos/<author>/2026-w19-...md
  Notes/<your hand-authored notes>
  Topics/<optional landing pages per tag>
  _taxonomy.md              — controlled vocabulary (15 starter tags; finance)
  _taxonomy-fitness.md      — fitness vocabulary
  _taxonomy-nutrition.md    — nutrition vocabulary
  _review-queue.md          — operator-in-the-loop checkboxes (finance)
  _review-queue-fitness.md  — fitness queue
  _review-queue-nutrition.md — nutrition queue
  _domains.yaml             — domain registry (scope rules); see "Multi-domain"
  .indexer/cache-finance.db    — finance sqlite cache; gitignored
  .indexer/cache-fitness.db    — fitness sqlite cache; gitignored
  .indexer/cache-nutrition.db  — nutrition sqlite cache; gitignored
```

## Frontmatter schema

```yaml
---
kind: book | book_chapter | newsletter | video | note | topic
title: "..."
author: "..."
source_url: "..."                  # videos, newsletters, articles
source_path: "/Users/.../foo.pdf"  # PDFs, EPUBs — operator's disk
source_sha256: "..."               # PDFs, EPUBs — robust to file moves
source_pdf_pages_total: 432        # PDFs only
published_at: 2026-05-15           # decay model uses this to rank same-author content
ingested_at: 2026-05-15T18:00Z
horizon_months: 6                  # legacy class-B horizon (still parsed, not used by new decay model)
evergreen: true                    # optional override; when present wins over path-glob default
parent: "Books/.../index.md"       # optional
tags: [liquidity, dollar_cycle]
---
```

**Decay model (Phase E Commit 2, supersedes exponential half-life):**

- **Evergreen** (frontmatter `evergreen: true` OR matches a domain's
  `evergreen_paths` glob) → weight = 1.0 (timeless reference content).
  Defaults: finance `Books/**`; fitness/nutrition `**`.
- **Sequential ranked-grouped** (finance non-evergreen): same `author`
  content ranked by `published_at` desc within the result set; ladder
  `[1.0, 0.6, 0.45, 0.35, 0.25]` applies per rank with the last rung as
  the floor for rank ≥ 5. Operator-confirmed shape: t >> t-1; t-1 > t-2;
  margin persists for adjacent ranks; floor reached after rank 4.
- **Off** (fitness/nutrition): weight = 1.0 for everything.
- **Ungrouped** (no `author`, e.g. `Filings/AAPL/...`, `Notes/...`,
  `Topics/...`) → weight = 1.0. No decay penalty applies.

## Ingestion CLIs

```bash
# PDF — layout-aware: detects chapter boundaries via embedded TOC →
# heading-scan → printed-Contents fallback. Filters running headers and
# footers, flags pages with figures / tables / landscape rotation, and
# warns when low-density pages suggest the PDF is a scan needing OCR.
python -m tools.vault_indexer.ingest.ingest_pdf \
  --path ~/Downloads/broken-money.pdf \
  --title "Broken Money" --author "Lyn Alden" --published 2024-09-30 \
  --tags "investing_classics"        # optional; comma-separated

# EPUB
python -m tools.vault_indexer.ingest.ingest_epub --path /path/to.epub

# Newsletter
python -m tools.vault_indexer.ingest.ingest_newsletter \
  --author lyn-alden --horizon 3 --url https://...

# Video (YouTube etc. via yt-dlp + openai-whisper)
python -m tools.vault_indexer.ingest.ingest_video \
  --author raoul-pal --horizon 3 \
  --url https://youtube.com/watch?v=...
```

Scheduled via launchd plists (macOS user agents). See `MULTI_DOMAIN_BRIEFING.md`
for the multi-domain plist pattern.

## Choices baked in

- **SQLite + sqlite-vec** over Postgres + pgvector — laptop pg image
  doesn't ship pgvector, and the indexer is cleaner self-contained.
- **bge-large-en-v1.5** (1024-d) over MiniLM-L6-v2 — strictly higher
  retrieval quality, native cosine, already cached.
- **Class B decay** = `exp(-age_months / (horizon/2))` — half-life =
  horizon/2. Operator overrides per-note via frontmatter.
- **Auto-tag** is off without `ANTHROPIC_API_KEY` — the indexer never
  writes to a note without operator approval.
- **Tags from a controlled vocabulary** in `_taxonomy.md`. Hand-edit:
  add lines, edit descriptions, remove tags, OR use the RENAMES block
  for atomic renames across every note's frontmatter.
- **Review queue is markdown** at `<vault>/_review-queue.md`. Operator
  ticks boxes in Obsidian; indexer reads ticks on next watch event.

See ADR-014 for the locked decisions.
