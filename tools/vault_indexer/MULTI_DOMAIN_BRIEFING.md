# Briefing — `vault_indexer` is now multi-domain

> **Audience**: any session, agent, or human operator working on the **TradingView finance app** that consumes `vault_indexer`. Read this before touching the indexer, the vault, or the launch scripts.

## TL;DR — what changed and what you must do

1. **The vault `~/Documents/knowledge-vault/` is now shared by two indexer instances**, one for finance (port 8001) and one for fitness (port 8002). They have **separate SQLite caches** and never see each other's content.
2. **The TradingView finance indexer (port 8001) MUST launch with `DOMAIN=finance` env set**. The indexer reads `<vault>/_domains.yaml` and derives the scope filter automatically. Without this env, the indexer scans fitness/nutrition folders and pollutes its cache. **This is the single most important rule in this document.**
3. **All code changes to `tools/vault_indexer/` are additive. Defaults preserve current behavior.** Old launches without env continue to work for legacy reasons but are no longer safe — see rule 2.
4. **Don't write to fitness folders, don't read `_taxonomy-fitness.md`, don't touch `cache-fitness.db`, don't bind port 8002.** Those belong to the fitness service.
5. **`ingest_video.py` is unchanged.** Behavior, CLI, and output paths identical to before. New ingester `ingest_queue.py` is fitness-only orchestration.
6. **`<vault>/_domains.yaml` is the single source of truth for domain partitioning.** Adding a new domain = one yaml entry. Finance auto-derives its EXCLUDE prefix from the registry; you don't update finance config when nutrition or any future domain is added.

If you do nothing else, do this:

```bash
# Always launch the finance indexer with this env. Make this the canonical
# launch invocation everywhere it's invoked (shell, launchd, etc.).
export DOMAIN=finance
cd "/Users/shourjosmac/Documents/Claude/TradingView "
venv/bin/python -m uvicorn tools.vault_indexer.app:app --port 8001 --host 127.0.0.1
```

The launchd plist at `~/Library/LaunchAgents/com.shourjo.kb-finance-indexer.plist` is the canonical persistent launcher; it bakes `DOMAIN=finance` in. Loading the plist (`launchctl load <path>`) is the recommended setup.

---

## What was added to `tools/vault_indexer/`

### 1. `config.py` — registry-aware tunables

`Config` is now an instance with `__init__` that reads several layers of input. **Three-tier precedence** for tunables that can vary by domain:

1. **Explicit env** (highest): `INCLUDE_FOLDERS`, `EXCLUDE_FOLDERS`, `TAXONOMY_FILE`, `REVIEW_FILE`, `DEFAULT_HORIZON_MONTHS`, `AUTO_TAG_ENABLED`. Use as escape hatches.
2. **Yaml-derived from `DOMAIN` env** (middle): when `DOMAIN=<slug>` is set, the indexer reads `<vault_path>/_domains.yaml` and derives values from the entry for that slug.
3. **Hardcoded default** (lowest): the same defaults the indexer used pre-change.

| Env var | Default | Purpose |
|---|---|---|
| `DOMAIN` | _(unset)_ | Domain slug. Resolves yaml entry → derives scope/taxonomy/review/horizon/auto-tag. Recommended single env. |
| `INCLUDE_FOLDERS` | _(empty)_ | Comma-separated path prefixes. Override yaml-derived include. |
| `EXCLUDE_FOLDERS` | _(empty)_ | Comma-separated path prefixes. Override yaml-derived exclude. Wins over INCLUDE. |
| `TAXONOMY_FILE` | `_taxonomy.md` | Override yaml-derived taxonomy filename. |
| `REVIEW_FILE` | `_review-queue.md` | Override yaml-derived review queue filename. |
| `DEFAULT_HORIZON_MONTHS` | `6` | Override yaml-derived decay horizon. |
| `AUTO_TAG_ENABLED` | `1` | Override yaml-derived auto-tag flag. |

A helper `passes_scope(rel_path: str) -> bool` lives in `config.py`. It's the one true entry point for include/exclude decisions:

```python
def passes_scope(rel_path: str) -> bool:
    """If exclude matches → False. If include is non-empty and no include
    matches → False. Otherwise True."""
```

Two new helpers `_load_domain_registry(vault_path)` and `_derive_scope_from_registry(domain, registry)` handle yaml parsing and derivation. Failure to parse yaml is silent (returns empty dict) so legacy launches without a registry continue to work.

### 2. `vault.py` — `scan()` now respects scope

`scan()` calls `passes_scope()` after `is_indexable()`. Finance launches with `DOMAIN=finance` (or explicit `EXCLUDE_FOLDERS`) set will silently skip fitness folders during the rglob walk. Behavior with no env vars set is identical to pre-change (everything indexable is scanned).

### 3. `renames.py` — RENAMES walker is scope-aware

`apply_renames(vault_root, taxonomy_file)` now also applies `passes_scope()` per file. This means:

- The finance service applying RENAMES from `_taxonomy.md` will only rewrite frontmatter on files that match its INCLUDE/EXCLUDE filter — so it can never inadvertently mutate fitness notes.
- The fitness service does the same in reverse.
- Critical: each RENAMES block is scoped to its own taxonomy file, but the rewriter walks the whole vault — without this filter, a rename in `_taxonomy.md` could silently rename a tag inside `Videos/fitness/...` (and vice versa).

### 4. `app.py` — uses `CONFIG.taxonomy_file`

The four hardcoded literals `CONFIG.vault_path / "_taxonomy.md"` were replaced with `CONFIG.vault_path / CONFIG.taxonomy_file`. Default value unchanged.

### 5. `review.py` — review queue file configurable, draft scanner scope-aware

Two changes:
- Module-level `REVIEW_FILE = "_review-queue.md"` became `REVIEW_FILE = CONFIG.review_file`. Default value unchanged.
- `_scan_pending_drafts(vault_root)` now applies `passes_scope()` to every `*.md.draft` it walks. Without this filter, the finance review queue (rendered into `_review-queue.md`) would surface fitness draft files left by the youtube_channel auto-ingest — operator would see fitness items in the finance review UI.

### 6. `cleanup_shorts.py` — Shorts walker is scope-aware

`find_shorts()` now applies `passes_scope()` per file. Without this filter, running `python -m tools.vault_indexer.cleanup_shorts` from a finance launch (with `DOMAIN=finance` set) would still walk fitness video folders and **delete** any fitness video whose `source_url` contains `/shorts/`. With the filter, fitness videos are invisible to the finance cleanup.

Behaviour preserved for legacy launches (no env → no filter → walks everything).

### 7. `ingest/youtube_channel.py` — channel discovery is scope-aware

`discover_channel_dirs(vault_root)` now applies `passes_scope()` to each `_channel.yaml` it finds under `<vault>/Videos/`. Without this filter, the finance auto-ingest orchestrator would discover fitness YouTube channels (e.g. `Videos/fitness/galpin/_channel.yaml`) and pull their videos into the finance corpus.

Behaviour preserved for legacy launches.

### 8. `ingest/ingest_queue.py` — **new file** (fitness-only orchestration)

Queue-driven YouTube ingester. Reads a markdown checklist file, dispatches `download_audio` + `transcribe` + `write_note` per unchecked URL, ticks `[x]` on success, leaves unchecked plus a comment on failure. Atomic rewrite, non-blocking flock. Optional `--reload-url` to refresh the indexer cache after a batch.

**Finance does not invoke this.** It is wired into the launchd plist `com.shourjo.kb-fitness-ingest`.

CLI:

```bash
PATH="$PWD/venv/bin:$PATH" venv/bin/python -m tools.vault_indexer.ingest.ingest_queue \
  --queue Videos/fitness/_ingest_queue.md \
  --rel-dir-prefix Videos/fitness \
  --reload-url http://127.0.0.1:8002/reload \
  --default-horizon 24
```

### 9. `ingest/ingest_video.py` — **unchanged**

Same CLI, same arguments, same default `--whisper-model small`, same output path `Videos/<author>/<week>-<slug>.md`. The `--whisper-model` choices list does **not** include `turbo`. If you wanted to use `turbo`, you'd need to amend the choices tuple — out of scope for this change.

---

## What was added to `~/Documents/knowledge-vault/`

### Folders (created empty, except where noted)

```
Videos/fitness/                   # fitness video transcripts land here
Videos/fitness/_ingest_queue.md   # new: URL drop point for fitness
Topics/fitness/                   # fitness concept hub notes
Newsletters/fitness/              # fitness newsletters (future)
Books/fitness/                    # fitness book ingests (future)
```

These four `*/fitness/` folders **must never be scanned by the finance indexer**. That's enforced by the `DOMAIN=finance` env on the finance service launch (the indexer derives the EXCLUDE list from `_domains.yaml`) — see rule 2.

### Files

- `_domains.yaml` — **the domain registry**. Single source of truth for what domains exist + their classes/taxonomy/review/horizon/auto-tag. The indexer reads this at startup based on the `DOMAIN` env. Adding a new domain = one yaml entry. Documented inline in the file.
- `_taxonomy-fitness.md` — controlled vocabulary for fitness (20 starter tags). **Finance reads `_taxonomy.md` only and never opens this file.**
- `_review-queue-fitness.md` — operator review queue for fitness (will be auto-generated by the fitness service on first `/reload`). **Finance never opens this file.**
- `Videos/fitness/_ingest_queue.md` — drop file for the queue ingester. The leading underscore means the indexer's `is_indexable` skips it (good — it's not content).

### SQLite caches

`.indexer/cache-finance.db` — **finance only**. Owned by the indexer running on port 8001. (Was `cache.db` in legacy single-domain installs; renamed for symmetry — see Phase E.5 retro in `.claude/status/roadmap-shipped.md`.)

`.indexer/cache-fitness.db` — **fitness only**. Owned by the indexer running on port 8002.

`.indexer/cache-nutrition.db` — **nutrition only**. Owned by the indexer running on port 8003.

The three caches are physically separate files. Even if a path filter ever broke, the worst case is bad data inside one cache; cross-pollination is structurally impossible because each service writes only to its own DB path.

---

## Ports and processes

| Port | Service | Process owner | Cache | Taxonomy | Review queue |
|---|---|---|---|---|---|
| 8001 | finance vault-indexer (TradingView reads from this) | `DOMAIN=finance` + `INDEXER_DB_PATH=.indexer/cache-finance.db` | `cache-finance.db` | `_taxonomy.md` | `_review-queue.md` |
| 8002 | fitness vault-indexer | `DOMAIN=fitness` + `INDEXER_DB_PATH=.indexer/cache-fitness.db` | `cache-fitness.db` | `_taxonomy-fitness.md` | `_review-queue-fitness.md` |
| 8003 | nutrition vault-indexer | `DOMAIN=nutrition` + `INDEXER_DB_PATH=.indexer/cache-nutrition.db` | `cache-nutrition.db` | `_taxonomy-nutrition.md` | `_review-queue-nutrition.md` |

Note: `INDEXER_DB_PATH` is per-instance because the cache file path is independent of the registry. Everything else (taxonomy file, review file, horizon, auto-tag, scope filter) derives from yaml. A boot-time coherence check warns if `DOMAIN` and `INDEXER_DB_PATH` disagree on which domain you're configuring (see `config.py`).

**Don't bind a port from a different domain.** Finance = 8001, fitness = 8002, nutrition = 8003.

---

## Launch scripts and launchd plists

### Finance launch — your responsibility

The finance service launchd plist is at `~/Library/LaunchAgents/com.shourjo.kb-finance-indexer.plist`. Its `EnvironmentVariables` block sets:
- `DOMAIN=finance` — the indexer reads `<vault>/_domains.yaml` and derives the EXCLUDE list automatically
- `INDEXER_DB_PATH=<vault>/.indexer/cache-finance.db` — explicit per-instance cache

Any other launcher (shell, CI, ad-hoc curl test against a fresh process) must set the same two vars. The escape hatches (`EXCLUDE_FOLDERS=…`, explicit alternate `INDEXER_DB_PATH`) remain for ad-hoc operation; the coherence-check warning in `config.py` will surface when DOMAIN and DB filename disagree.

### Adding a new domain — recipe

End-to-end steps when you want a fourth indexer (e.g. `macro`):

1. **Vault content.** Place markdown under `<vault>/<Class>/macro/...` (e.g. `Books/macro/...`, `Videos/macro/...`).
2. **Registry.** Append to `<vault>/_domains.yaml`:
   ```yaml
   macro:
     classes: [Books, Newsletters, Videos, Topics]
     taxonomy_file: _taxonomy-macro.md
     review_file: _review-queue-macro.md
     default_horizon_months: 12
     auto_tag_enabled: false
   ```
   Finance auto-derives the new EXCLUDE prefix (since it's `legacy: true`); no other yaml edits required.
3. **Vocabulary stubs.** `touch <vault>/_taxonomy-macro.md <vault>/_review-queue-macro.md` (empty markdown is fine; indexer regenerates the review queue on first `/reload`).
4. **launchd plist.** Copy `com.shourjo.kb-fitness-indexer.plist` → `com.shourjo.kb-macro-indexer.plist`, change Label, port (8004), and `EnvironmentVariables`: `DOMAIN=macro`, `INDEXER_DB_PATH=<vault>/.indexer/cache-macro.db`.
5. **kb-mcp source.** Edit `~/.config/kb-mcp/sources.yaml` to add `macro: http://127.0.0.1:8004` under the `knowledge_vault` source's `endpoints` block.
6. **Load + verify.** `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.shourjo.kb-macro-indexer.plist`; `curl http://127.0.0.1:8004/health`; restart Claude Desktop so kb-mcp picks up the new endpoint.
7. **Ingest.** `curl -X POST http://127.0.0.1:8004/reload` (or wait for the daily reload-sweep agent if it covers your endpoint).
8. **Verify isolation.** `sqlite3 <vault>/.indexer/cache-macro.db "SELECT COUNT(*) FROM vault_node WHERE path NOT LIKE 'Books/macro/%' AND path NOT LIKE 'Videos/macro/%' AND path NOT LIKE 'Newsletters/macro/%' AND path NOT LIKE 'Topics/macro/%';"` should return `0`. The `test_vault_indexer_domain_isolation.py` integration test exercises this same guarantee in CI.

### launchd plists — loaded and active

| Plist | Schedule | Effect |
|---|---|---|
| `com.shourjo.kb-finance-indexer` | always-on (KeepAlive) | port 8001 |
| `com.shourjo.kb-fitness-indexer` | always-on (KeepAlive) | port 8002 |
| `com.shourjo.kb-nutrition-indexer` | always-on (KeepAlive) | port 8003 |
| `com.shourjo.kb-fitness-ingest` | daily 01:00 local | polls `Videos/fitness/_ingest_queue.md` for both YouTube videos AND web articles (defuddle path). retries with cap=3 then quarantines |
| `com.shourjo.kb-nutrition-ingest` | daily 04:00 local | polls `Videos/nutrition/_ingest_queue.md`, same dual-mode |
| `com.shourjo.kb-reload-sweep` | daily 07:00 local | POSTs `/reload` on every indexer endpoint discovered in `~/.config/kb-mcp/sources.yaml`. Diff-aware indexer makes this cheap. Self-healing for ingest→reload-ping failures. |
| `com.shourjo.kb-hub-drafter` | weekly Sun 03:00 local | reads `Topics/<domain>/_concepts_to_draft.md` per domain, retrieves top-K chunks, drafts hub notes via Claude Haiku, writes `*.md.draft` for review |

Schedule rationale: staggered 01/04/07 so heavy CPU jobs don't collide while user has other apps running (Chrome / Docker / Spotify / etc). Fitness gets 01:00 because its queues can be largest. Nutrition gets 04:00 (3h buffer). Reload-sweep at 07:00 catches any straggler from the night.

These do not affect finance in any way (finance ingest is via TradingView's own `youtube_channel.py` poller, not via these queue plists). Don't `launchctl unload` them by accident.

**Manual trigger any time**:
```bash
launchctl start com.shourjo.kb-fitness-ingest
launchctl start com.shourjo.kb-nutrition-ingest
launchctl start com.shourjo.kb-reload-sweep
```

---

## Whisper cache state

`~/.cache/whisper/` contains `small.pt` (484 MB). This is the model `ingest_video.py` uses by default. `large-v3-turbo.pt` was briefly downloaded during planning then deleted (it wasn't in the existing `--whisper-model` choices list, so couldn't be used without a code change). No other model is cached locally; running with `--whisper-model large-v3` will trigger a one-time ~3 GB download of `large-v3.pt` on first use.

---

## Things you must NOT do

1. **Don't launch the finance indexer without `DOMAIN=finance`** (or, equivalently, an explicit `EXCLUDE_FOLDERS` for back-compat). It will scan fitness content and the finance app will surface it.
2. **Don't add finance content under `Videos/fitness/`, `Topics/fitness/`, `Newsletters/fitness/`, or `Books/fitness/`.** Even if the slug is the same as a finance author, those folders are claimed by fitness.
3. **Don't write a finance video into `Videos/fitness/<finance-author>/`.** Use `Videos/<finance-author>/` (no `fitness/` segment).
4. **Don't share `cache-fitness.db` or read it from the finance service.** It's the fitness service's private store. There is no finance use case for it.
5. **Don't bind anything else to port 8002.** Reserved for fitness service.
6. **Don't add fitness tags to `_taxonomy.md` or finance tags to `_taxonomy-fitness.md`.** Each service has its own controlled vocabulary file.
7. **Don't apply RENAMES that span domains.** A rename in `_taxonomy.md` only rewrites finance notes (because of the `passes_scope` filter in `renames.py`). If you want a tag rename to span both, you must add the rename to both taxonomy files.
8. **Don't strip `DOMAIN` (or `EXCLUDE_FOLDERS`) from any test or CI invocation of the indexer pointing at the real vault.** Spin up a tmpfs vault for tests instead.
9. **Don't downgrade these env-handling code paths** — the additive defaults rely on env-handling existing.
10. **Don't trigger `/reload` on `:8001` from a script that doesn't first verify the env is set.** Easy way: have the script `curl :8001/health` and abort if `vault` ≠ `~/Documents/knowledge-vault`. Stronger: add a `/scope` endpoint later that returns the active include/exclude config. For now, an env preflight in your launcher is fine.

---

## Verification recipes

### Confirm finance is filtering correctly

```bash
# Health
curl -sS http://127.0.0.1:8001/health

# Drop a fitness probe and trigger reload — finance should NOT see it.
mkdir -p ~/Documents/knowledge-vault/Videos/fitness/probe-test
cat > ~/Documents/knowledge-vault/Videos/fitness/probe-test/probe.md <<EOF
---
kind: video
title: filter probe
author: probe
domain: fitness
horizon_months: 12
tags: []
---
# probe
zone 2 training mitochondrial biogenesis. should NOT appear in finance results.
EOF

curl -sS -X POST http://127.0.0.1:8001/reload
curl -sS 'http://127.0.0.1:8001/search?q=zone%202%20mitochondrial&k=10' | jq '.results | map(.path)'
# Expected: empty list, or finance-only results. NEVER `Videos/fitness/probe-test/probe.md`.

# Cleanup
rm -rf ~/Documents/knowledge-vault/Videos/fitness/probe-test
curl -sS -X POST http://127.0.0.1:8001/reload    # drop the probe from cache
```

### Confirm fitness is isolated

```bash
curl -sS http://127.0.0.1:8002/health
# Should report db = .../cache-fitness.db (different from :8001's).

# Search the fitness index for a finance-flavoured query.
curl -sS 'http://127.0.0.1:8002/search?q=federal%20reserve&k=10' | jq '.results | length'
# Expected: 0 (until any fitness video happens to discuss it).
```

### Confirm scope filter logic without touching disk

```bash
cd "/Users/shourjosmac/Documents/Claude/TradingView "
DOMAIN=finance venv/bin/python -c "
from tools.vault_indexer.config import CONFIG
from tools.vault_indexer.vault import scan
fitness_seen = [n.rel_path for n in scan(CONFIG.vault_path) if 'fitness' in n.rel_path or 'nutrition' in n.rel_path]
print('non-finance nodes seen by finance scan:', fitness_seen)
print('total finance nodes:', sum(1 for _ in scan(CONFIG.vault_path)))
print('derived exclude:', CONFIG.exclude_folders)
"
# Expected: fitness_seen=[], derived exclude has 8 prefixes (4 per non-legacy domain in registry).
```

---

## What hasn't been built yet

- **Phase 3 (MCP wrapper for Claude Code)** — not done. Claude Code currently consumes `:8001` and `:8002` via raw `curl`. A small Python `fastmcp` server wrapping `kb_search`, `kb_traverse`, `kb_node`, `kb_topics` is the planned next step but is not blocking finance behavior.
- **Phase 5 (concept hub auto-draft)** — not done. Will run after first fitness ingest batch. Doesn't affect finance.
- **Phase 6 (nutrition domain)** — already pre-declared in `_domains.yaml`. When the nutrition service spins up (`DOMAIN=nutrition` + own `INDEXER_DB_PATH`), finance auto-derives the new EXCLUDE prefixes on next restart. **No finance config update required** — that's the whole point of the registry.

If you ever need the registry change to affect a running finance service without restarting, add the prefixes manually via `EXCLUDE_FOLDERS` env override, then restart.

---

## Failure modes and recovery

### Symptom: finance `/search` returns a fitness chunk

**Cause**: finance was launched without `DOMAIN=finance` (or pre-registry `EXCLUDE_FOLDERS`), or the registry yaml was malformed and the indexer fell through to defaults.

**Recovery**:
1. Stop the finance service.
2. Set `DOMAIN=finance`. Verify `<vault>/_domains.yaml` parses correctly (`yaml.safe_load`).
3. Drop the finance cache (rebuildable in <10 min): `rm ~/Documents/knowledge-vault/.indexer/cache-finance.db*` (matches `.db`, `.db-wal`, `.db-shm`).
4. Restart the finance service.
5. POST `/reload`.
6. Re-run the verification recipe above.

### Symptom: fitness service crashes / port 8002 unreachable

**Cause**: most likely a missing env var or a vault path issue.

**Recovery**: check `~/Library/Logs/kb-fitness-indexer.err`. Common issues:
- `VAULT_PATH` not pointing at an existing dir.
- `INDEXER_DB_PATH` parent (`.indexer/`) doesn't exist (it should — the original cache lives there too).

### Symptom: queue ingester runs but does nothing

Check `~/Library/Logs/kb-fitness-ingest.log`:
- "queue file not found" → check the path is `Videos/fitness/_ingest_queue.md` relative to `VAULT_PATH`.
- "yt-dlp not on PATH" → the launchd PATH env is wrong; should include `<TradingView>/venv/bin`.
- "another ingest run is active" → previous run still going (long video transcribing). Wait.

### Symptom: a tag rename in `_taxonomy.md` didn't propagate

Each service rewrites only its own scope. If you want a rename to apply across both domains, add the rename line to **both** `_taxonomy.md` and `_taxonomy-fitness.md`, then trigger `/apply-renames` on **both** ports.

---

## File map (canonical paths)

```
~/Documents/Claude/TradingView /tools/vault_indexer/
  config.py                      MODIFIED (registry + 3-tier env precedence; defaults preserve behavior)
  vault.py                       MODIFIED (scan() applies passes_scope)
  renames.py                     MODIFIED (RENAMES walker scope-aware)
  app.py                         MODIFIED (taxonomy path uses CONFIG.taxonomy_file)
  review.py                      MODIFIED (REVIEW_FILE config + _scan_pending_drafts scoped)
  cleanup_shorts.py              MODIFIED (find_shorts() applies passes_scope)
  ingest/youtube_channel.py      MODIFIED (discover_channel_dirs applies passes_scope)
  ingest/ingest_queue.py         NEW (fitness queue ingester)
  ingest/ingest_video.py         UNCHANGED
  README.md                      MODIFIED (n8n reference replaced with launchd)
  MULTI_DOMAIN_BRIEFING.md       NEW (this file)
  FINANCE_TEAM_WRITEUP.md        NEW (sister doc for finance team)

~/Documents/Claude/TradingView /
  .env.laptop                    MODIFIED (DOMAIN=finance appended)

~/Documents/knowledge-vault/
  _domains.yaml                  NEW (domain registry — single source of truth)
  Videos/fitness/                NEW (folder)
  Videos/fitness/_ingest_queue.md NEW
  Topics/fitness/                NEW (folder)
  Newsletters/fitness/           NEW (folder)
  Books/fitness/                 NEW (folder)
  _taxonomy-fitness.md           NEW
  _review-queue-fitness.md       will be auto-generated on first :8002 /reload
  _taxonomy.md                   UNCHANGED
  _review-queue.md               UNCHANGED
  .indexer/cache-finance.db      finance only (renamed from cache.db in Phase E.5)
  .indexer/cache-fitness.db      fitness only
  .indexer/cache-nutrition.db    nutrition only

~/Library/LaunchAgents/
  com.shourjo.kb-finance-indexer.plist   NEW (DOMAIN=finance baked in; not yet loaded)
  com.shourjo.kb-fitness-indexer.plist   NEW (DOMAIN=fitness baked in; not yet loaded)
  com.shourjo.kb-fitness-ingest.plist    NEW (queue poller; not yet loaded)

~/Library/Logs/
  kb-finance-indexer.log/.err            written when plist loaded
  kb-fitness-indexer.log/.err            written when plist loaded
  kb-fitness-ingest.log/.err             written when plist loaded
```

---

## One-line summary you can paste into a future Claude session

> The vault `~/Documents/knowledge-vault/` is shared between two `vault_indexer` instances. Finance runs on :8001 and **must** launch with `DOMAIN=finance` (the indexer reads `<vault>/_domains.yaml` and derives the EXCLUDE list automatically); otherwise it will absorb fitness content. Fitness runs on :8002 with its own cache, taxonomy, and review queue, derived the same way from `DOMAIN=fitness`. Adding a new domain is a one-line edit to `_domains.yaml`. Code changes in `tools/vault_indexer/` are additive (defaults preserve old behavior). Read `tools/vault_indexer/MULTI_DOMAIN_BRIEFING.md` for full detail.
