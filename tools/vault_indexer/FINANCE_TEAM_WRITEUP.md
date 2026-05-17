# vault-indexer multi-domain change — write-up for finance team

**Audience**: TradingView finance app developers and on-call operators.
**Purpose**: explain what changed in `tools/vault_indexer/`, why it changed, and how to diagnose and recover if the finance app exhibits unexpected behavior.
**Companion document**: [`MULTI_DOMAIN_BRIEFING.md`](./MULTI_DOMAIN_BRIEFING.md) — full technical reference.

> **Update (2026-05-16, Phase E.5):** the finance cache file was renamed from `cache.db` to `cache-finance.db` for symmetry with `cache-fitness.db` / `cache-nutrition.db`. Behaviour is unchanged — the rename is cosmetic. Statements below that say `cache.db` are historical and refer to the legacy filename; substitute `cache-finance.db` for any present-day operational command. A boot-time coherence check in `config.py` now warns if `DOMAIN` and `INDEXER_DB_PATH` disagree about which domain the operator intends to configure. Full retro in [`.claude/status/roadmap-shipped.md`](../../.claude/status/roadmap-shipped.md) ("Vault-indexer retrieval speedup + domain-config symmetry — Phase E").

---

## TL;DR

The personal knowledge vault at `~/Documents/knowledge-vault/` is now used by **two** indexer processes — one for finance (port 8001, your existing service) and one for fitness (port 8002, new). They share the same on-disk vault but maintain **independent SQLite caches** and never see each other's content.

For finance, **one operational change matters**: every launch of `tools/vault_indexer/app.py` for finance must include the env var:

```
DOMAIN=finance
```

The indexer reads `<vault_path>/_domains.yaml` (the domain registry) and derives the scope filter automatically. Adding a new domain (e.g. nutrition, wellness, …) is a one-line edit to that yaml — finance gets the new EXCLUDE prefix automatically with no env update on the finance side.

Everything else in the indexer's behavior, schema, API, and outputs is unchanged. All code edits are additive with defaults that preserve legacy behavior. Existing finance launches that don't set `DOMAIN` will keep working but **will leak** fitness/nutrition content into the finance cache (legacy `cache.db`, now `cache-finance.db`). The env is the safety boundary.

**Escape hatch**: explicit `EXCLUDE_FOLDERS=...` (the pre-registry pattern) still works and overrides the registry. Useful for ad-hoc CLI invocations or emergency operation when the registry is corrupt.

---

## Why this change happened

The operator wants to use the same machine and same vault to also accumulate world-centric knowledge in **other domains** — initially fitness (Andy Galpin, Andrew Huberman transcripts), with nutrition planned next. These transcripts are massive (multi-hour episodes ⇒ hundreds of thousands of tokens). They need to be searchable through the same indexer machinery — the operator already trusts this stack — but they must **never be returned** by the finance app's `/search` or `/traverse` calls. Showing zone-2 cardio chunks in a Fed-meeting query would be a UX disaster and would erode trust in the finance app's grounding.

Three architectural options were considered:

| Option | Verdict |
|---|---|
| Single indexer + caller-side domain filter | Rejected. Soft isolation; any forgotten filter (debug curl, cron, future feature) leaks fitness content into finance results. |
| Separate vault for fitness | Rejected. Loses the cross-domain semantic graph that's the whole point of using a shared embedding store. |
| **Two indexer processes, shared vault on disk, separate caches** | **Adopted.** Hard isolation by construction (different `cache.db` files); zero TradingView app code changes; cross-domain queries possible later via federation if needed. |

The chosen design isolates by partitioning the **scanner's input set** at indexer startup: the finance instance refuses to scan fitness/nutrition folders, the fitness instance refuses to scan everything else. Each writes only to its own SQLite cache. Cross-pollination requires both code-level filters AND DB writes from the wrong process — structurally implausible.

---

## What changed in `tools/vault_indexer/`

All changes are additive. Default behavior with no env vars is identical to the pre-change indexer. Finance app dev team should treat this as a transparent improvement plus one mandatory env var.

### New env vars (all optional with safe defaults)

Finance only needs `DOMAIN=finance`. The rest are escape-hatch overrides.

| Env var | Default | Effect on finance |
|---|---|---|
| `DOMAIN` | _(unset)_ | Finance **must set to `finance`**. Reads `_domains.yaml` registry, derives include/exclude/taxonomy/review/horizon/auto-tag for the named domain. |
| `INCLUDE_FOLDERS` | _(empty)_ | Finance leaves this **unset** (used by the fitness instance via its `DOMAIN`). Explicit set overrides the registry. |
| `EXCLUDE_FOLDERS` | _(empty)_ | Finance leaves this **unset**; the registry derives it from `DOMAIN=finance`. Explicit set overrides the registry. |
| `TAXONOMY_FILE` | `_taxonomy.md` | Finance leaves at default. |
| `REVIEW_FILE` | `_review-queue.md` | Finance leaves at default. |
| `DEFAULT_HORIZON_MONTHS` | `6` | Finance leaves at default. |
| `AUTO_TAG_ENABLED` | `1` | Finance leaves at default. |

### Domain registry — `<vault>/_domains.yaml`

Single source of truth for domain partitioning. Finance is the **legacy catch-all** — its corpus stays where it is (`Books/`, `Newsletters/lyn-alden/`, `Videos/click-capital/`, etc.), and finance scope is "everything not under another domain". Other domains live at `<Class>/<slug>/<author>/...`.

```yaml
domains:
  finance:
    legacy: true
    taxonomy_file: _taxonomy.md
    review_file: _review-queue.md
  fitness:
    classes: [Books, Newsletters, Videos, Topics]
    taxonomy_file: _taxonomy-fitness.md
    review_file: _review-queue-fitness.md
    default_horizon_months: 24
    auto_tag_enabled: false
  nutrition:
    classes: [Books, Newsletters, Videos, Topics]
    ...
```

When `DOMAIN=finance` is set, indexer derives `EXCLUDE_FOLDERS` = ⋃ `<Class>/<other-slug>` for every non-legacy entry. Adding a `wellness` domain to the yaml automatically adds `Books/wellness, Newsletters/wellness, Videos/wellness, Topics/wellness` to finance's EXCLUDE on next restart.

When `DOMAIN=fitness` is set, indexer derives `INCLUDE_FOLDERS` = `Books/fitness, Newsletters/fitness, Videos/fitness, Topics/fitness`.

### New helper

`config.passes_scope(rel_path: str) -> bool` — single source of truth for include/exclude decisions. Used by every place in the indexer that walks the vault filesystem.

### Files modified (8 total)

All edits are minimal — typically a single import + a single filter call.

| File | Change | Risk if env misconfigured |
|---|---|---|
| `config.py` | Added 4 env vars + `passes_scope()` helper | None alone |
| `vault.py` | `scan()` skips paths failing `passes_scope` | High — main scanner; controls what gets embedded |
| `renames.py` | RENAMES walker only mutates files in scope | Tag renames could rewrite fitness notes from finance taxonomy |
| `app.py` | 4 hardcoded `_taxonomy.md` paths → `CONFIG.taxonomy_file` | None alone (default preserves) |
| `review.py` | `REVIEW_FILE` config-driven; `_scan_pending_drafts` scoped | Finance review queue surfaces fitness draft files |
| `cleanup_shorts.py` | `find_shorts()` skips paths failing `passes_scope` | **Destructive** — could delete fitness Shorts videos |
| `ingest/youtube_channel.py` | `discover_channel_dirs()` skips paths failing `passes_scope` | Finance auto-ingest could pull fitness channel content |
| `ingest/ingest_video.py` | **Unchanged** | n/a |

### Files added

| File | Role |
|---|---|
| `ingest/ingest_queue.py` | New CLI for the fitness service. Polls a markdown checklist, ingests via existing `ingest_video` helpers, atomically rewrites the file. **Finance does not invoke this.** |
| `MULTI_DOMAIN_BRIEFING.md` | Engineering reference. Living doc. |
| `FINANCE_TEAM_WRITEUP.md` | This document. |

---

## What the finance app must do

### One required action

Wherever the finance indexer is launched — local shell, launchd plist, supervisor script, CI, ad-hoc curl tests — set the env:

```bash
export DOMAIN=finance
```

Then launch as before:

```bash
cd "/Users/shourjosmac/Documents/Claude/TradingView "
venv/bin/python -m uvicorn tools.vault_indexer.app:app --port 8001 --host 127.0.0.1
```

The canonical persistent setup is the launchd plist at `~/Library/LaunchAgents/com.shourjo.kb-finance-indexer.plist`, which bakes `DOMAIN=finance` into its `EnvironmentVariables` block. Loading the plist (`launchctl load <path>`) is the recommended production-style launch — it survives reboots and you can never forget the env.

`.env.laptop` also carries `DOMAIN=finance` for shell launches that source it.

### Things that did NOT change

- The HTTP API (`/health`, `/search`, `/traverse`, `/reload`, `/promote`, `/apply-renames`, `/regenerate-review`, `/node/{path}`) — same surface, same response shapes.
- The SQLite schema in `cache.db`. Existing rows are unaffected.
- The default `--whisper-model small` for `ingest_video`. The choices list is unchanged.
- The taxonomy file `_taxonomy.md`, the review queue file `_review-queue.md`, the auto-tag flow, the decay formula, the chunking parameters.
- `app/research/` and `app/tv_context/` (TradingView app code). They consume the indexer through the HTTP API, so they get correctly-scoped data automatically as long as the indexer was launched with the env above.

---

## Unexpected behavior — diagnosis playbook

### Symptom 1: `/search` returns a chunk whose `path` starts with `Videos/fitness/...` or `Topics/fitness/...` etc.

**Meaning**: cache pollution. The finance indexer scanned a fitness folder at some point.

**Most likely root cause**: a launch happened without `DOMAIN=finance` (or pre-registry `EXCLUDE_FOLDERS`) in the env. Possibilities to check, in order:
1. The current running process — was it launched from a shell where the env wasn't exported? `ps aux | grep uvicorn` and inspect.
2. A supervisor / launchd plist that forgot to inherit the env.
3. A developer running an ad-hoc `uvicorn` or `python -m tools.vault_indexer.app` for testing.
4. A `POST /reload` triggered while the env was missing during a hot-reload window.

**Recovery**:

```bash
# 1. Stop the finance service.
launchctl unload <plist>     # or kill the uvicorn PID

# 2. Reset env. Verify it's set.
export DOMAIN=finance
echo "$DOMAIN"

# 3. Drop the polluted cache. It's rebuildable in <10 minutes.
#    (Post Phase E.5: the file is `cache-finance.db`. Drop WAL + SHM too.)
rm ~/Documents/knowledge-vault/.indexer/cache-finance.db*

# 4. Restart. The cache rebuilds clean.
cd "/Users/shourjosmac/Documents/Claude/TradingView "
venv/bin/python -m uvicorn tools.vault_indexer.app:app --port 8001 --host 127.0.0.1

# 5. Verify with the recipe in the next section.
```

`full_rescan` in `indexer.py` self-cleans nodes whose files weren't seen during the scoped scan, so even without dropping `cache.db`, the next `/reload` after the env is fixed will purge the leaked rows. Dropping the file is the belt-and-suspenders option when you want a guaranteed clean slate.

### Symptom 2: `/search` returns fewer results than expected for a finance query

**Meaning**: scope filter may be too aggressive.

**Diagnose**:
```bash
echo $DOMAIN $EXCLUDE_FOLDERS
# If DOMAIN=finance and registry is healthy, EXCLUDE is auto-derived correctly.
# If EXCLUDE_FOLDERS is set explicitly, check it: did someone add a bare `Videos/`
# (no domain suffix) by accident? That would exclude the entire Videos tree.
DOMAIN=finance venv/bin/python -c "from tools.vault_indexer.config import CONFIG; print(CONFIG.exclude_folders)"
# Inspect the derived list — should be 4 prefixes per non-finance domain in _domains.yaml.
```

Both `EXCLUDE_FOLDERS` and `INCLUDE_FOLDERS` use **prefix matching**. A bare `Videos` excludes the entire Videos directory. Registry-derived values are always per-domain (`Videos/fitness`, etc.) — only manual env overrides risk this kind of typo.

### Symptom 3: A finance YouTube Shorts file disappeared after running `cleanup_shorts`

**Meaning**: this should never happen now, but if it did, the env wasn't applied to the cleanup CLI.

**Diagnose**:
```bash
# Make sure the env reaches the CLI process. cleanup_shorts reads the same env as the server.
DOMAIN=finance python -m tools.vault_indexer.cleanup_shorts --dry-run
```

If the dry run lists fitness/nutrition shorts despite the env being set, the filter logic isn't being applied — see "Verification §3" below to test `passes_scope` directly.

### Symptom 4: A tag rename in `_taxonomy.md`'s RENAMES block didn't propagate to all expected notes

**Expected**: `apply_renames` only rewrites notes that pass the finance scope. Fitness notes are never rewritten by the finance instance. If a tag is shared across domains and you want both renamed, the rename must be added to **both** `_taxonomy.md` AND `_taxonomy-fitness.md`, then `/apply-renames` triggered on **both** ports.

### Symptom 5: `_review-queue.md` shows a draft for a fitness video

**Meaning**: `_scan_pending_drafts` ran without the env. Same root cause as symptom 1 — env missing. Same recovery.

### Symptom 6: Finance auto-ingest started pulling fitness videos

**Meaning**: `youtube_channel.discover_channel_dirs()` ran without the env. Same root cause — env missing. Same recovery, plus delete any fitness video files that were drafted into finance folders.

### Symptom 7: Finance app `app/research/service.py` writes a research note into `Videos/fitness/...`

**Meaning**: shouldn't happen. Research notes write to a path computed from indexer search results; if `/search` is scoped correctly, every returned `path` is finance-scoped. If you see a write into a fitness folder, the indexer was leaking — see symptom 1. Repair the indexer first; the research write was a downstream symptom.

### Symptom 8: The fitness service competing with finance for ports / RAM / CPU

**Diagnose**:
```bash
lsof -nP -i:8001 -i:8002       # confirm one process per port
ps aux | grep uvicorn          # confirm no zombies
```

The fitness service loads bge-large-en-v1.5 (~1.5 GB RAM at idle). On a 16 GB Mac that's fine but if RAM pressure is a concern, the fitness service can be stopped (`launchctl unload`); finance is unaffected because the caches are physically separate files.

### Symptom 9: The indexer process won't start at all

**Diagnose**: check stderr / launchd log.
- "vault not found" → `VAULT_PATH` env points at a non-existent directory.
- sqlite-vec or HF model load errors → the venv is stale; `pip install -r requirements.txt` from inside the venv.

### Symptom 10: `cache.db` schema doesn't match what TradingView expects

This change introduced no schema changes. If you see a schema mismatch, it's from a pre-existing migration in your branch, not from this work.

---

## Verification recipes — run after any indexer restart or env change

### §1 — Runtime health

```bash
curl -sS http://127.0.0.1:8001/health
# Expected: {"status":"ok","vault":".../knowledge-vault","db":".../cache-finance.db",...}
# (Pre-2026-05-16: the file was named `cache.db`. The Phase E.5 rename gave
#  each domain a `cache-<domain>.db` filename for symmetry. If your install
#  still has the legacy `cache.db` name, it's not broken — just renamed
#  manually with `mv` after stopping the launchd agent. See §Migration below.)
```

### §2 — Probe-based isolation test (positive control)

This proves both that the filter is active AND that the test setup itself is real (i.e. the test would have failed if the filter were broken).

```bash
# Drop a fitness probe.
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
# Expected: [] or finance-only results. NEVER `Videos/fitness/...`.

# Cleanup
rm -rf ~/Documents/knowledge-vault/Videos/fitness/probe-test
curl -sS -X POST http://127.0.0.1:8001/reload   # drop the probe row from cache
```

### §3 — Scope filter unit test (no disk writes)

```bash
cd "/Users/shourjosmac/Documents/Claude/TradingView "
DOMAIN=finance venv/bin/python -c "
from tools.vault_indexer.config import CONFIG, passes_scope
from tools.vault_indexer.vault import scan
from tools.vault_indexer.review import _scan_pending_drafts
from tools.vault_indexer.ingest.youtube_channel import discover_channel_dirs

assert not passes_scope('Videos/fitness/galpin/foo.md')
assert not passes_scope('Topics/nutrition/protein.md')
assert passes_scope('Videos/lyn-alden/2026-w19.md')
assert passes_scope('Newsletters/raoul-pal/foo.md')

fitness_seen = [n.rel_path for n in scan(CONFIG.vault_path) if 'fitness' in n.rel_path or 'nutrition' in n.rel_path]
assert fitness_seen == [], f'leak: {fitness_seen}'

drafts = _scan_pending_drafts(CONFIG.vault_path)
assert all('fitness' not in d['path'] and 'nutrition' not in d['path'] for d in drafts)

channels = [str(p) for p in discover_channel_dirs(CONFIG.vault_path)]
assert all('fitness' not in c and 'nutrition' not in c for c in channels)

print('ok')
"
```

If this prints `ok`, every filter site enforces scope correctly under the configured env.

### §4 — App-side smoke test

After restart, run a small set of TradingView app queries that previously returned known-good results. Spot-check that:
- The same finance authors appear.
- No path under any of the excluded prefixes appears.
- Result counts are within ±5% of pre-change baselines (slight differences possible from stale cache rebuild rounding).

---

## Scaling considerations (forward-looking)

When the operator adds a new domain (nutrition is already pre-declared in `_domains.yaml`; future ones might be wellness, productivity, etc.), the procedure is:

1. Edit `<vault>/_domains.yaml` to add the entry.
2. Spin up the new indexer with `DOMAIN=<new-slug>` env (and a unique `INDEXER_DB_PATH`).
3. Restart the finance service (or `POST /reload`). It re-reads the registry and auto-derives the new EXCLUDE prefixes.

**Finance config does not change** when new domains are added. The registry is the single point of update.

If you need finance to ignore the registry (e.g. emergency operation): set `EXCLUDE_FOLDERS` explicitly. It overrides the yaml-derived list.

---

## Recovery cheatsheet

| Situation | Command |
|---|---|
| Stop finance | `launchctl unload <plist>` or `kill $(lsof -ti:8001)` |
| Restart finance with env | `DOMAIN=finance venv/bin/python -m uvicorn tools.vault_indexer.app:app --port 8001 --host 127.0.0.1` |
| Load finance launchd plist | `launchctl load ~/Library/LaunchAgents/com.shourjo.kb-finance-indexer.plist` |
| Drop polluted cache | `rm ~/Documents/knowledge-vault/.indexer/cache-finance.db*` (matches `.db` + `.db-wal` + `.db-shm`; rebuildable in <10 min) |
| Force fresh scan | `curl -sS -X POST http://127.0.0.1:8001/reload` |
| Verify env in current process | `lsof -nP -p $(lsof -ti:8001) | head` then check the env via `ps eww <PID>` |
| Test scope filter | See §3 above |

---

## Contact / ownership

- **Indexer code owner**: same team that owns `tools/vault_indexer/` historically.
- **Vault owner**: operator (Sho).
- **Fitness service owner**: not the finance app team — the fitness service runs in parallel and consumes from the operator's domain. Finance team does not need to operate or debug it; if finance health is fine, fitness is irrelevant.

---

## File map (post-change)

```
~/Documents/Claude/TradingView /tools/vault_indexer/
  config.py                      MODIFIED  registry + 3-tier env precedence
  vault.py                       MODIFIED  scan() applies filter
  renames.py                     MODIFIED  RENAMES walker scoped
  app.py                         MODIFIED  taxonomy file via env
  review.py                      MODIFIED  REVIEW_FILE via env + draft scanner scoped
  cleanup_shorts.py              MODIFIED  find_shorts scoped
  ingest/youtube_channel.py      MODIFIED  channel discovery scoped
  ingest/ingest_queue.py         NEW       (fitness queue ingester — finance unused)
  ingest/ingest_video.py         UNCHANGED
  cache.py | search.py | excerpt.py | decay.py | auto_tag.py |
  taxonomy.py | research_hook.py | cleanup_filings.py | indexer.py
                                 UNCHANGED
  README.md                      MODIFIED  n8n reference replaced with launchd
  MULTI_DOMAIN_BRIEFING.md       NEW (engineering reference)
  FINANCE_TEAM_WRITEUP.md        NEW (this document)

~/Documents/Claude/TradingView /
  .env.laptop                    MODIFIED  DOMAIN=finance appended

~/Documents/knowledge-vault/
  _domains.yaml                  NEW       (domain registry — single source of truth)
  Videos/fitness/, Topics/fitness/, Newsletters/fitness/, Books/fitness/
                                 NEW       (fitness folders, empty)
  _taxonomy-fitness.md           NEW
  .indexer/cache-fitness.db      NEW       (fitness cache)
  .indexer/cache-finance.db      RENAMED   (was `cache.db` pre-Phase-E.5; same content)

~/Library/LaunchAgents/
  com.shourjo.kb-finance-indexer.plist   NEW  DOMAIN=finance baked in (not loaded yet)
  com.shourjo.kb-fitness-indexer.plist   NEW  DOMAIN=fitness baked in (not loaded yet)
  com.shourjo.kb-fitness-ingest.plist    NEW  queue poller (not loaded yet)
```

---

*Last updated 2026-05-10. Update this section if the indexer changes again.*
