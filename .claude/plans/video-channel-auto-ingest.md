# Plan — Video channel auto-ingest (`_channel.yaml`)

## Context

Operator wants new YouTube videos from subscribed channels to be auto-pulled into the vault on a daily schedule (or per-channel cadence), with operator approval gating canonical entry. Newsletters get the same treatment later — same shape, different fetcher.

## Decisions locked

1. **Trigger**: hourly lifespan task, per-channel cadence respected via `last_polled_at` in YAML. **No webhook**, no n8n.
2. **Source of truth per channel**: `Videos/<channel>/_channel.yaml` next to `_index.md`. Single artifact per channel.
3. **Schema**:
   ```yaml
   # Videos/fx-evolution-daily/_channel.yaml
   channel_id: UCxxxxx                 # YouTube channel ID
   channel_url: https://youtube.com/@fx-evolution-daily
   author: <creator name>              # used as `author` in ingested files + auto-tag seed
   default_kind: video
   default_horizon_months: 6           # decay-weight floor for these videos
   default_tags: [macro, fx]           # seeded into auto-tag review-queue suggestion
   ingest:
     enabled: true                     # master switch per channel
     cadence: daily                    # 'daily' | 'weekly' | 'manual'
     auto_promote: false               # if true, skip review queue (high-trust channels only)
     prefer_captions: true             # try YouTube captions first; whisper fallback
     last_polled_at: 2026-05-06T08:00:00Z   # machine-managed
     last_video_id: <yt-id>            # machine-managed; dedupe sentinel
     seen_video_ids: [<id1>, <id2>]    # last 50, FIFO; dedupe across reboots
   ```
4. **Fetch strategy**:
   - Channel feed: `https://www.youtube.com/feeds/videos.xml?channel_id=<id>` — RSS, no auth, no quota, returns last 15 videos.
   - Captions: `yt-dlp --skip-download --write-auto-sub --sub-format vtt --sub-lang en` — free, instant, ≥80% hit rate on macro/finance channels.
   - Whisper fallback: only when captions absent. Already installed.
   - Audio download via `yt-dlp -f bestaudio` if whisper triggers.
5. **Render template** (per video, written to `<published_at>-<slug>.md.draft`):
   ```markdown
   ---
   kind: video
   title: "<title>"
   author: <author from _channel.yaml>
   source_url: https://youtube.com/watch?v=<id>
   video_id: <id>
   published_at: <ISO>
   ingested_at: <ISO>
   horizon_months: <default_horizon_months>
   parent: Videos/<channel>/_index.md
   tags: <default_tags from _channel.yaml>
   draft: true
   ---

   # <title>

   *<channel author> · <published_at> · [Watch](source_url)*

   ## Summary
   <Haiku 1-paragraph summary of captions>

   ## Transcript
   <full captions or whisper output>
   ```
6. **Operator approval flow**:
   - Lifespan task writes `.md.draft` files + appends entries to `_review-queue.md` (existing queue mechanism).
   - Operator opens `_review-queue.md` in Obsidian, ticks `[x]` next to each they want to keep.
   - Indexer's `/promote` endpoint detects ticks, renames `.md.draft` → canonical name (drops `.draft` suffix and `draft: true` from frontmatter), runs auto-tag. Untacked drafts left alone (operator can delete later).
   - `auto_promote: true` channels skip review queue — drafts are immediately promoted on creation.
7. **Failure handling**:
   - RSS fetch fails → log + skip channel that tick → retry next tick.
   - Captions absent → fall back to whisper. If whisper fails → log + skip video; don't write a partial draft.
   - YouTube schema change → catch + log + skip (operator notices via empty review queue + log).
8. **Newsletters later**: same pattern. New module `newsletter_channel.py` + `_channel.yaml` with `default_kind: newsletter`. Fetcher uses RSS too (Substack, Beehiiv, Ghost expose `/feed`).

## Files touched

### New
- `tools/vault_indexer/ingest/youtube_channel.py` — fetcher: RSS poll, captions, whisper fallback, render template, write draft + review-queue entry.
- `tools/vault_indexer/ingest/_channel_yaml.py` — load/save helpers; manages `seen_video_ids` rolling window.
- `app/main.py` — add lifespan task `video_ingest_loop()` (env-gated by `VIDEO_INGEST_ENABLED=true`, default false).

### Modified
- `tools/vault_indexer/research_hook.py` (or `app/promote/`) — extend `_promote` flow to handle `.md.draft` → canonical rename when ticked.
- `app/core/config.py` — env var `VIDEO_INGEST_ENABLED` (default false). `VIDEO_INGEST_CADENCE_FLOOR_MIN_HOURS=1` (skip channels polled in last hour even if cadence is 'daily').
- `requirements.txt` — `yt-dlp`, `feedparser` (`whisper-large-v3` already present from prior session).
- `tests/test_youtube_channel.py` — new file. Mock RSS fetch, captions presence/absence, dedup logic, draft naming.

## Out of scope (deferred)

1. **Newsletter channels** — same shape, separate module. Defer until video flow is in steady use.
2. **Multi-source dedup** — same video uploaded across two channels. Detect by `video_id` (yt's UCID is global). Drop the duplicate. Ship.
3. **Adaptive cadence** — channel publishes weekly but YAML says daily. Auto-detect + suggest cadence drop. Defer.
4. **Drift between operator's `_index.md` and channel content** — Haiku quarterly check. Belongs to plan #1's drift-detection followup, not here.
5. **N8n bridging** — explicitly skipped; lifespan task is the chosen vector.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| YouTube rate-limits the RSS endpoint | L | Daily poll on ≤10 channels = trivial. RSS has no documented quota. Cap at hourly per-channel via cadence floor. |
| Whisper takes too long on a 1hr video | M | Run whisper in `asyncio.to_thread`. Acceptable: 30min video ≈ 30min wall on M3 CPU. Block lifespan loop only for that channel; others continue. |
| `yt-dlp` requires updates frequently when YouTube changes internals | M | Pin a recent stable version; bump quarterly. Document in tech_debt.md if updates lag. |
| Draft files pollute the vault if operator ignores review queue for weeks | L | Reuse vault-indexer's review-queue gc; expire untouched drafts after 30 days (config). |
| `auto_promote: true` channel publishes garbage one day | M | Operator can edit `_channel.yaml` to flip back; promoted file can be deleted in Obsidian. Cheap reversibility. |
| Captions get auto-translated and read incorrectly | L | Set `--sub-lang en` explicitly. Skip videos without English subs. |

## Verification

1. Write `_channel.yaml` for one trusted channel (operator picks).
2. Set `VIDEO_INGEST_ENABLED=true` on laptop.
3. Restart laptop FastAPI.
4. Confirm lifespan task fires; check logs for `video_ingest_loop: polling Videos/<channel>`.
5. Confirm at least one video lands as `.md.draft` in the channel folder.
6. Confirm entry appears in `_review-queue.md`.
7. Tick the entry. Run `POST :8001/promote`.
8. Confirm draft renamed (no `.draft` suffix), `draft: true` removed from frontmatter, auto-tag suggestion in queue.
9. Trigger a research query mentioning the channel's topic — confirm the new video chunk appears in evidence.

## Effort

- yt-dlp + RSS + caption flow: **3 hrs**
- whisper fallback wiring: **1.5 hrs**
- render template + review-queue integration: **2 hrs**
- promote flow handling drafts: **1 hr**
- lifespan task + env wiring: **1 hr**
- tests: **2 hrs**
- E2E verify on real channel: **1 hr**
- **Total: ~11 hrs**, ~1.5 sessions

## Dependencies / blockers

- `yt-dlp` install (operator confirms ok)
- whisper-large-v3 already installed (per prior session). Confirm no GPU dep — runs CPU.
- Operator picks first channel + supplies channel_id. (Channel ID is in the channel URL when the URL uses /channel/UC..., or visible in the page source for /@handle URLs.)

## Sequencing

Execute **plan #1 first** (folder-context vignettes). Plan #2 builds on top: lifespan task that creates new files needs to populate `parent: Videos/<channel>/_index.md` correctly, which only matters when `_index.md` is in use.
