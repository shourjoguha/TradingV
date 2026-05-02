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
| `INDEXER_DB_PATH` | `<VAULT_PATH>/.indexer/cache.db` | Created on first run. |
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

## Endpoints

| | |
|---|---|
| `GET /health` | Sanity probe. |
| `POST /reload` | Apply pending RENAMES + full vault rescan + regenerate review queue. |
| `GET /node/{path:path}` | Raw node row (frontmatter + body). |
| `GET /search?q=&k=` | Decay-weighted KNN over chunks. |
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
  _taxonomy.md         — controlled vocabulary (15 starter tags)
  _review-queue.md     — operator-in-the-loop checkboxes
  .indexer/cache.db    — sqlite cache; gitignored
```

## Frontmatter schema

```yaml
---
kind: book | book_chapter | newsletter | video | note | topic
title: "..."
author: "..."
source_url: "..."
published_at: 2026-05-15
ingested_at: 2026-05-15T18:00Z
horizon_months: 6      # class B only; null/missing → 6mo default
parent: "Books/.../index.md"   # optional
tags: [liquidity, dollar_cycle]
---
```

Class A (`book`, `book_chapter`, `note`, `topic`) → decay weight 1.0.
Class B (`newsletter`, `video` or any note in a timely folder) →
`weight = exp(-age_months / (horizon/2))`.

## Ingestion CLIs

```bash
# PDF
python -m tools.vault_indexer.ingest.ingest_pdf \
  --path ~/Downloads/broken-money.pdf \
  --title "Broken Money" --author "Lyn Alden" --published 2024-09-30

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

n8n drives these — see [.claude/vault.md](../../.claude/vault.md) for the
trigger-graph pattern.

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
