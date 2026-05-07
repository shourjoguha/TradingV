# Plan — Folder context vignettes (`_index.md`)

## Context

Operator wants to author a markdown context file at any level of the vault (`Videos/_index.md`, `Videos/fx-evolution-daily/_index.md`, etc.) that captures **unstated invariants** about the folder's contents — things the chunks don't repeat (creator background, default chart filters, default time grain, sequence of presentation, etc.). This context must be **always prepended** to the research bundle whenever any descendant chunk hits, in addition to the KNN evidence list.

Operator has decided: **no token cap on operator-authored bodies**. If they took the time to write it, it ships verbatim.

## Decisions locked

1. **File convention**: `_index.md` at any level under `<vault>/`. Lives in vault, edited in Obsidian, tracked in git.
2. **Frontmatter contract**:
   ```yaml
   ---
   kind: folder_context        # new kind enum value
   title: "FX Evolution Daily — channel context"
   author: <optional>
   ingested_at: <auto>
   ---
   ```
   Body = free-form markdown.
3. **Indexer behavior**: `_index.md` files (or any node with `kind: folder_context`) are stored in `vault_node` but **never chunked into `vault_chunk_vec`**. They never appear in KNN evidence — only in the new "source context" channel.
4. **Bundle behavior**: after `_retrieve_evidence` completes, walk each evidence chunk's vault_path UPWARD; collect every `_index.md` on the path. Deduplicate. Attach to bundle as new top-level `source_context: [{path, title, body, applies_to: [evidence_paths]}, ...]`.
5. **Truncation**: source_context is **NOT trimmed** by `_truncate`. Operator-authored content is sacrosanct. Truncation order remains: oldest evaluations → low-score evidence → trim longest evidence body. Source context is excluded from the loop.
6. **Prompt rendering**: new "## Source context" section in user message, between hypothesis cards and evidence list. Each entry rendered as `### {title} ({path})\n\n{body}`.
7. **Frontend rendering**: AnswerCard gains a "Source context" collapsible block before Evidence. Same accordion primitive.

## Files touched

### Backend
- `tools/vault_indexer/cache.py` — no schema change needed (the `kind='folder_context'` rows just don't get chunks). Add helper `parent_index_files(con, evidence_paths) -> list[dict]`.
- `tools/vault_indexer/indexer.py` — skip embedding step when `kind == 'folder_context'`.
- `tools/vault_indexer/app.py` — new endpoint `POST /folder-context` that takes `{"paths": [...]}` and returns `{"items": [{path, title, body, applies_to}]}`.
- `tools/vault_indexer/taxonomy.py` (or wherever kind enum lives) — add `folder_context` to allowed kinds.
- `app/research/bundle.py` — call new endpoint after `_retrieve_evidence`; attach `source_context` to bundle. Update `_truncate` to skip it.
- `app/research/prompts.py` — render new section; cache_control: ephemeral on the bundle prefix still applies (source_context lands inside the cached prefix).
- `app/research/schemas.py` — add `source_context: list[SourceContextItem]` to `AskResponse` + `ResearchQueryRead`. Update `_flatten_*` helpers in `service.py`.
- `app/research/service.py` — `_flatten_source_context()` helper.

### Frontend
- `frontend/src/lib/types.ts` — `SourceContextItem` interface; extend `AskResponse` + `ResearchQueryRead`.
- `frontend/src/components/research/AnswerCard.tsx` — render `<SourceContextSection items={...}/>` between verdict and evidence.
- `frontend/src/components/research/SourceContextSection.tsx` — new file. Accordion of full-body markdown.

### Tests
- `tests/test_research.py` — `test_bundle_includes_source_context_for_evidence_paths`. Mocks indexer to return one evidence path under `Videos/fx-evolution-daily/`; asserts `source_context` in response contains the channel's `_index.md` body verbatim.
- `tests/test_vault_indexer.py` — `test_folder_context_kind_skips_embedding` (assert no chunks created for `kind=folder_context` files).

## Behavior on pre-existing vault data

- Vault doesn't have any `_index.md` files yet → bundle works exactly as today (`source_context: []`).
- After operator writes one and runs `/reload` on indexer → bundle picks it up on next query.

## Out of scope

- Frontend authoring UI. Operator writes `_index.md` in Obsidian.
- Auto-generation by Haiku. Always manual for v1.
- Drift detection. Operator owns staleness.

## Verification

1. Write a real `_index.md` at `Videos/fx-evolution-daily/_index.md` (operator does this).
2. Reload indexer (`POST :8001/reload`).
3. Run `/v1/research/ask` with a query that retrieves a chunk under `Videos/fx-evolution-daily/`.
4. Confirm response.source_context contains the `_index.md` body verbatim.
5. Confirm prompt rendered to Claude includes the source context block.
6. Confirm UI AnswerCard shows Source context section.

## Risks

| Risk | Mitigation |
|---|---|
| operator writes `_index.md` without `kind: folder_context` frontmatter — indexer chunks it like a regular note and it pollutes evidence | Validate in `indexer.py`: any file named `_index.md` is auto-coerced to `kind: folder_context` regardless of frontmatter. Operator-friendly. |
| Multiple parent levels each have an `_index.md` (Videos/_index.md AND Videos/fx-evolution-daily/_index.md) — both attach | Intended. Both get prepended in path order (root → leaf). |
| Token bloat if operator writes a 10k-word `_index.md` | Accepted per operator decision. No cap. |
| `_index.md` body changes don't update bundle until `/reload` | Existing pattern; `/reload` is one click. |

## Effort

- Backend (indexer + bundle + tests): **2 hrs**
- Frontend (SourceContextSection + AnswerCard wiring): **1 hr**
- Verification on real vault: **30 min**
- **Total: ~3.5 hrs**
