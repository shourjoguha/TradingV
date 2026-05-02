# Knowledge vault + indexer

Operator's personal evidence layer. Markdown vault on disk, indexed by a
sidecar service that TradingView reads from. Phase 2 of the
macro-workbench → decision-tool roadmap (shipped 2026-05-02).

> **Source-of-truth:** the vault. The indexer's SQLite cache at
> `<vault>/.indexer/cache.db` is fully rebuildable. Nuke and re-embed in
> <10 min if anything goes sideways.

## What lives where

```
~/Documents/knowledge-vault/      ← operator's space (Obsidian-real)
  Books/                          ← class A (timeless)
  Newsletters/<author>/           ← class B (decay)
  Videos/<author>/                ← class B (decay)
  Notes/                          ← class A; operator-authored
  Topics/                         ← class A; optional landing pages per tag
  _taxonomy.md                    ← 15-tag controlled vocabulary; hand-editable
  _review-queue.md                ← indexer-managed; operator ticks checkboxes
  .indexer/cache.db               ← SQLite + sqlite-vec; gitignored

tools/vault_indexer/              ← FastAPI sidecar; port 8001
  ingest/                         ← PDF / EPUB / newsletter / video CLIs
```

## Choices

- **Authoring style: B-mode (low discipline).** Embeddings carry
  cross-connectivity, tags carry operator intent, folders carry
  hierarchy. Wikilinks are optional polish — not required for the graph
  to work.
- **Embedder:** `BAAI/bge-large-en-v1.5` (1024-d, cosine-native, cached).
  Query-side prefix `"Represent this sentence for searching relevant
  passages: "` per bge guidance; passages encoded raw.
- **Storage:** SQLite + sqlite-vec (loaded via `apsw`, since Apple's stock
  Python disables loadable extensions). Decoupled from TradingView's
  Postgres.
- **Decay** for class B: `weight = exp(-age_months / (horizon/2))`.
  Half-life = horizon / 2. Class A always weight = 1.0. Operator can
  override per-note via `horizon_months: null` to mark a class-B note as
  timeless.
- **Vocabulary** is small (~15 tags, in `_taxonomy.md`). Free-form tags
  are flagged in the review queue as vocabulary candidates rather than
  silently accepted.
- **Auto-tag** uses Claude Haiku (`claude-haiku-4-5`) constrained to the
  vocabulary. Off when `ANTHROPIC_API_KEY` is missing — the indexer never
  writes a tag the operator didn't tick.

See [ADR-014](decisions/014-vault-indexer.md) for the full decision
record.

## Frontmatter

```yaml
---
kind: book | book_chapter | newsletter | video | note | topic
title: "..."
author: "..."
source_url: "..."             # videos, newsletters, articles
source_path: "..."            # PDFs, EPUBs — absolute path on operator's disk
source_sha256: "..."          # PDFs, EPUBs — re-locate the file if it moves
source_pdf_pages_total: 432   # PDFs only — total page count of the original
source_pages: [32, 60]        # PDFs only — chapter's start/end page (1-indexed)
published_at: 2026-05-15
ingested_at: 2026-05-15T18:00Z
horizon_months: 6
parent: "Books/.../index.md"
tags: [liquidity, dollar_cycle, chapter_has_landscape]
---
```

`tags` may include automatic `chapter_has_figures` / `chapter_has_tables`
/ `chapter_has_landscape` when the layout analyzer detects images,
table-shaped layouts, or rotated text in a chapter's pages. These let
the operator filter Obsidian for chapters with charts without re-reading
the index.

The `source_*` breadcrumb keeps the door open for a future
**vision-retrieval** workflow (read a specific PDF page or video frame
on-demand to extract chart values, equations, or table fidelity that
text extraction can't preserve). The original PDF/EPUB stays in the
operator's library — **not** copied into the vault. `source_sha256`
makes the breadcrumb robust to file moves. See the deferred backlog
entry "Vision retrieval over original sources" for the trigger
condition.

## Operator-edit flows

### Adding a tag
Open `_taxonomy.md`, add a bullet under "Active tags". Indexer reloads
on save. Future auto-tag suggestions can use it.

### Editing a description
Rewrite text after the dash on the bullet line. Affects only the
auto-tag prompt context; existing tagged notes are unchanged.

### Removing a tag
Delete the bullet. Notes already tagged with the removed name retain
the tag in their frontmatter; orphans are flagged in `_review-queue.md`
so the operator can re-tag manually or accept as deprecated.

### Renaming a tag
Add a line to the RENAMES block at the bottom of `_taxonomy.md`:

```
old_name → new_name
```

On the next watch event (or `POST /apply-renames`), the indexer rewrites
every note's frontmatter atomically and strips the directive from the
taxonomy file. Idempotent.

## Operator-in-the-loop review

Indexer regenerates `_review-queue.md` on every `/reload`,
`/regenerate-review`, or `/promote`. Operator opens the file in Obsidian,
ticks checkboxes (auto-tag suggestions, cross-link suggestions), saves.

Next time the indexer runs (or operator hits `POST /promote`):
1. Read ticks from the queue.
2. For each ticked tag: append it to the note's frontmatter `tags:`.
3. For each ticked link: insert an explicit `wikilink` edge into
   `vault_edge`.
4. Full rescan to refresh the cache.
5. Rewrite `_review-queue.md` with a fresh batch.

The queue file is the entire review API. No separate UI.

## Running it

```bash
export VAULT_PATH=$HOME/Documents/knowledge-vault
uvicorn tools.vault_indexer.app:app --port 8001
```

**Cache persistence:** `<vault>/.indexer/cache.db` survives restarts.
Laptop reboots / uvicorn restarts do **not** trigger re-embedding —
embedding is one-time per markdown file (re-runs only on body-hash
change). Restart uvicorn and the corpus is searchable again on first
request. Operator runbook: [`use_me_guide.md`](../use_me_guide.md) §1.5.

## Endpoints (port 8001)

| | |
|---|---|
| `GET  /health` | sanity |
| `POST /reload` | RENAMES + rescan + regenerate review |
| `GET  /node/{path:path}` | node row |
| `GET  /search?q=&k=` | decay-weighted KNN |
| `GET  /traverse/{path:path}?depth=N` | local subgraph |
| `POST /promote` | apply review-queue ticks |
| `POST /apply-renames` | manual rename trigger |
| `POST /regenerate-review` | rebuild queue without ingesting |

No auth — laptop-local. TradingView calls it over loopback. If the
indexer ever moves off-laptop, add an API-key middleware identical to
TradingView's pattern.

## TradingView integration

Phase 2 added the `hypothesis_node_links` pointer table; Phase 3 made it
load-bearing. The vault-indexer's `/promote` flow now also scans
`Research/*.md` for ticked Approve/Dismiss boxes and HTTP-calls
TradingView's `/v1/research/queries/{id}/approve|dismiss` — see
[research.md](research.md). Two new env vars (`TRADINGVIEW_API_URL`,
`TRADINGVIEW_API_KEY`) drive that coupling.

```sql
hypothesis_node_links(
  hypothesis_id FK→hypothesis,
  vault_path TEXT,                          -- e.g. "Newsletters/.../foo.md"
  stance ('supports'|'challenges'|'context'),
  added_at, added_by ('operator'|'auto'),
  PRIMARY KEY (hypothesis_id, vault_path)
)
```

Vault-path is canonical and not FK-enforced because the indexer's cache
is in a separate SQLite DB. TradingView validates against the indexer at
write time.

## n8n trigger pattern

n8n owns the trigger graph (RSS, YouTube playlist watch, email parsing).
A trigger fires `python -m tools.vault_indexer.ingest.ingest_X ...` over
SSH to the laptop. The script writes markdown into the vault. The
indexer's watch loop picks it up within ~2 seconds; manual fallback is
`POST /reload`.

## Out of scope (Phase 3+)

- TradingView's `/v1/research/ask` endpoint (bundle assembler + Claude
  tool-use). Phase 3.
- Wikilink-graph parsing in the indexer — operator B-mode doesn't author
  them. Add later if authoring habits change.
- Multi-vault support.
- An Obsidian plugin. The vault works with vanilla Obsidian.
- Auto-promote at high confidence. Off by default; can be flipped via
  config when the operator finds the review-tick discipline draining.
