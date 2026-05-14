# video_vision — local frame OCR for ingested videos

## Why

The audio transcript captures what's *said* in a video. It misses what's *shown* on screen — chart types, periodic windows ("1D"/"Weekly"), source attributions ("FRED"/"TradingView"/"Bloomberg"), tickers visible in the chart axis, key prices written on annotations, on-screen polls. These micro-references are rich operator signal that never gets voiced over.

`tools/vault_indexer/ingest/video_vision.py` adds a "Visual notes" markdown section to ingested videos by extracting scene-change frames and running Tesseract OCR. **Local-only, zero API spend, no image persistence.** Domain-agnostic — works for any channel (finance, fitness, nutrition, future categories).

## Three-stage filter (why frames don't multiply unboundedly)

| Stage | What it does | Default |
|---|---|---|
| 1. **Pixel-change threshold** | ffmpeg `select=gt(scene,T)` filters frames where ≥ T% of pixels meaningfully changed. Rejects cursor wiggles (≈0.0005%) while catching ticker swaps on the same chart layout (≈30-50%). | `scene_threshold: 0.10` |
| 2. **Time-gap dedupe** | Collapse consecutive scene cuts within N seconds — presenters hold a chart for the audience to read. Keep the first frame; ignore subsequent micro-fluctuations. | `min_gap_seconds: 10` |
| 3. **SSIM redundancy filter** (optional) | Drop frames whose structural similarity with the previous keeper exceeds threshold. Catches "presenter tabbed away and came back to the same chart." Falls back to no-op when `scikit-image` not installed. | `ssim_threshold: 0.92` |
| 4. **Budget cap** | If still over `frame_budget`, keep top scene-score in budget, restore time order. | `frame_budget: 50` |

Threshold reasoning (operator-locked):
| Visual event | Pixel diff | Captured? |
|---|---|---|
| Cursor wiggle | ~0.0005% | No |
| Subtitle change | ~2-3% | No |
| Ticker swap (same chart layout) | ~30-50% | Yes |
| Full screen cut | ~70-95% | Yes |
| Slide/fade transition | ~50-80% | Yes |
| Zoom on chart | ~15-30% | Yes |

## Per-channel YAML schema

Drop a `vision:` block onto ANY `_channel.yaml`. Absent block = vision disabled (default).

```yaml
# Videos/<channel>/_channel.yaml
vision:
  enabled: true               # default false everywhere
  frame_budget: 50            # max frames per video after dedupe
  scene_threshold: 0.10       # ffmpeg select=gt(scene,X) threshold
  min_gap_seconds: 10         # Stage-2 hold-time dedupe
  ssim_threshold: 0.92        # Stage-3 redundancy; null disables
  ocr_lang: eng               # Tesseract language pack
  semantic_captions: false    # L3 (Moondream2) — not implemented yet
```

## Storage footprint (operator's "no image persistence" rule)

| Thing | Size | Notes |
|---|---|---|
| Tesseract binary + English pack | ~50MB | One-time `brew install tesseract`. Smaller than the existing Whisper-small (~484MB). |
| Video file during ingest | 0 | `TemporaryDirectory()` — deleted on context exit |
| Extracted frame PNGs | 0 | Same temp dir |
| Markdown visual-notes section | ~1-5 KB per video | The only thing that persists; lives in the vault as searchable content |

**Image data NEVER persists past the ingest run.** Both the downloaded video and extracted frames live inside `tempfile.TemporaryDirectory()` inside `youtube_channel.py:ingest_one()`. The OS deletes them on block exit (normal exit OR exception).

## Pilot CLI

Run a dry-run on a single video to inspect signal quality before flipping a channel:

```bash
cd ~/Documents/Claude/TradingView
PATH="$PWD/venv/bin:$PATH" ./venv/bin/python -m tools.vault_indexer.ingest.video_vision \
    --url 'https://www.youtube.com/watch?v=<recent-vid>' \
    --frame-budget 30 \
    --scene-threshold 0.10 \
    --min-gap-seconds 10 \
    --dry-run
```

Prints the rendered markdown to stdout. No vault writes. No image persistence.

## Multi-domain reuse (operator-confirmed)

Same module, same code path, same toggle — works for any indexer scope:

| Folder | Indexer | Works? |
|---|---|---|
| `Videos/fx-evolution-daily/` | finance :8001 | ✓ (enabled) |
| `Videos/click-capital/` | finance :8001 | ✓ (enabled) |
| `Videos/fitness/<channel>/` | fitness :8002 | ✓ flip the YAML block |
| `Videos/nutrition/<channel>/` | future :8003 | ✓ flip the YAML block |
| Any net-new domain | new indexer instance | ✓ flip the YAML block |

For non-English channels, set `ocr_lang: eng+fra` (or similar). Install extra language packs: `brew install tesseract-lang`.

## Kill switch

Two ways to disable:
1. Set `vision.enabled: false` (or remove the block) on a specific channel.
2. Module guards: missing `ffmpeg`, `yt-dlp`, or `tesseract` binaries → graceful no-op; ingest proceeds with audio-only transcript.

## Failure handling

Every external boundary returns `""` or empty `VisionResult` on error rather than raising:
- yt-dlp download fails → no markdown, diagnostics record `reason: download_failed`
- ffmpeg scene-detect returns zero frames → no markdown, `reason: no_scene_frames`
- Tesseract reads garbage → quality filter drops the row; remaining rows still render
- scikit-image not installed → Stage 3 (SSIM) becomes a no-op; Stage 1+2 still run

`render_visual_notes_table([])` returns `""` — no orphan `## Visual notes` heading when nothing usable comes through.

## Structured chart references (Phase A/A2/B/C — 2026-05-14)

Beyond free-form captions, channels with `vision.chart_extraction.enabled: true` get **structured chart-reference extraction** — Stage 1 Qwen2-VL emits YAML/JSON with `chart_type`, `timeframe`, `tickers`, `topics`, `caption` fields; Stage 2 (Python heuristic in `chart_extractor.py`) regex-salvages anything that didn't parse; Stage 3 last-resort regex extracts individual fields directly from raw output.

**End-to-end signal recovery (2026-05-14 pilot, click-capital):** 5 frames → 5 structured chart_references emitted. Even on YAML/JSON parse failure, the regex-salvage path captures `chart_type` + `timeframe` + `tickers` + `caption` fields independently.

### Channel YAML schema (extended)

```yaml
vision:
  enabled: true
  frame_budget: 50
  scene_threshold: 0.10
  min_gap_seconds: 10
  ssim_threshold: 0.92
  ocr_lang: eng
  semantic_captions: true       # L3 free-form captions
  chart_extraction:             # NEW — Phase A/A2/B/C
    enabled: true               # default OFF; finance channels only
    rollup_cap: 10              # entries kept in channel _index.md
```

### What lands in the vault

**Per-video frontmatter** gains:

```yaml
chart_references:
  - timestamp: "5:27"
    timestamp_seconds: 327.0
    chart_type: line
    timeframe: 1h
    tickers: [AAPL, MSFT, AMZN]
    topics: [AI infrastructure, Fed minutes, bubble parallel]
    caption: "If you weren't trading in 1999-2000..."
visual_notes_strategy: L3-structured
```

**Per-video body** gains a one-line summary block above the Visual Notes table:

```markdown
**Charts referenced (5):** 2× line, 1× bar, 1× candlestick (1d), 1× gauge
**Timeframes:** 4h, 1d, 1w
**Tickers:** BTC, META, AAPL
**Topics:** AI bubble parallel, semiconductor boom, Fed minutes
```

**Per-channel `_index.md`** gains a sentinel-bounded auto-section:

```markdown
<!-- AUTO:chart-references:start -->
## Recent chart references (auto-generated)

| Date | Video | Charts |
|---|---|---|
| 2026-05-14 | [the-bull-and-bear-statue](Videos/click-capital/2026-W19-foo.md) | BTC (4h candlestick); NASDAQ (line) |
| 2026-05-13 | [semiconductor-boom](Videos/click-capital/2026-W19-bar.md) | KOSPI (1d candlestick) |

_Auto-generated; operator-edited content above and below this block is preserved._
<!-- AUTO:chart-references:end -->
```

Operator-authored content above and below the sentinel markers is **preserved across upserts**. Dedupe key is `rel_path` (markdown link target); FIFO eviction at `rollup_cap`. The vault-indexer's `/folder-context` endpoint returns `_index.md` verbatim, so research bundles + hypothesis stress-tests inherit this signal automatically.

### Ticker whitelist

Stage 2 heuristic ticker extraction filters against the dynamic union of:
- Operator's `watchlist` table (roster)
- All `boards` tickers
- The Street tier-1/2 from the last 4 snapshots

Loaded fresh at the start of each video ingest via `chart_extractor.load_ticker_whitelist_sync()`. False positives like `AI`, `USA`, `GDP` are filtered by a static stoplist even with empty whitelist.

### Three-stage extraction chain

| Stage | What it does | Source |
|---|---|---|
| 1. Qwen2-VL structured YAML/JSON | LLM-extracted full structured output | `vlm_adapter.caption_frame_structured` |
| 2. Heuristic regex on caption text | Stage 2 backfill via regex on prose | `chart_extractor.extract_from_caption` |
| 3. Field-by-field regex salvage from raw output | Last-resort recovery on parse failure | `vlm_adapter._regex_salvage` |

Stage 3 is critical — Qwen2-VL frequently outputs JSON-fenced-as-YAML with subtle invalidities (trailing commas, hallucinated repeats). The field-by-field regex catches `chart_type: line` / `timeframe: 4h` / `tickers: ['BTC']` patterns regardless of overall validity.

### Files

- `tools/vault_indexer/ingest/vlm_adapter.py` — Stage 1 + Stage 3 (regex salvage)
- `tools/vault_indexer/ingest/chart_extractor.py` — Stage 2 heuristic + whitelist loader
- `tools/vault_indexer/ingest/vignette_updater.py` — channel `_index.md` upsert
- `tools/vault_indexer/ingest/video_vision.py` — orchestrator
- `tools/vault_indexer/ingest/youtube_channel.py` — render_draft + vignette wiring

### Deferred to Commit 2 (next session)

- **Ticker review queue** — Stage 1 emits tickers NOT in the whitelist; currently logged-only (`unknown_tickers` field on VisionResult). Phase D wires them to a new `app/ticker_review/` module with DB queue + Today UI strip + Sunday Obsidian digest. Plan: `.claude/plans/ok-now-we-have-distributed-anchor.md` "Phase D" section.

## L3 — semantic captions via MLX Qwen2-VL (Apple Silicon)

Enable per channel with `vision.semantic_captions: true`. Adds a "Visual" column to the visual-notes table with a one-line VLM-generated caption per frame. Independent of OCR — captions and OCR are two signals that combine in a 3-column table.

**Model:** `mlx-community/Qwen2-VL-2B-Instruct-4bit` via `mlx-vlm`. ~1GB disk (cached at `~/.cache/huggingface/` on first run). MLX-accelerated on M1/M2/M3/M4. Originally planned as Moondream2 — `mlx-vlm` 0.5.x doesn't ship moondream2 weights yet, and Qwen2-VL gives similar size at competitive chart-reading quality.

**Performance on M3:**
- Model load (one-time per process): ~10-15s
- Per-frame inference: ~1-2s
- 50-frame video: ~60-100s captioning added on top of L2

**Caption answers operator's "what kind of chart, what timeframe" question:**
- "candlestick chart type, displaying a timeframe of 4H (4-hour)"
- "The chart type is a line chart, and the timeframe..."
- "Fear & Greed Index gauge"
- "bull and a bear statue ... bear market"

**Failure modes:** all return empty caption gracefully:
- MLX unavailable (non-Apple-Silicon, mlx-vlm not installed) → empty caption, table falls back to 2-column
- Model load fails (network down, repo renamed) → poisoned cache, all subsequent frames empty caption
- Single-frame inference error → empty caption, other frames continue

**Kill switches:**
- Per-channel: `vision.semantic_captions: false` → no VLM calls, table back to 2-column
- Global: `DISABLE_MLX_VLM=1` env var → adapter pretends MLX unavailable
- Code: uninstall `mlx-vlm` from venv

## Whisper backend (MLX/torch adapter)

Whisper transcription goes through `tools/vault_indexer/ingest/whisper_adapter.py` which routes to MLX on Apple Silicon (3-5× speedup vs torch CPU) or falls back to openai-whisper. Same audio bytes in, same text out — single touchpoint for the platform check.

**Override:** `FORCE_TORCH_WHISPER=1` env var → use torch path even on M3 (debugging).

**Models:** `mlx-community/whisper-{tiny,base,small,medium,large-v3-mlx}`. Default `small` matches the existing operator preference.

## Files

- `tools/vault_indexer/ingest/video_vision.py` — pipeline + CLI
- `tools/vault_indexer/ingest/youtube_channel.py` — `ingest_one()` reads `cfg.vision`, calls `video_vision.process_video()` inside the existing temp-dir scope, threads `visual_notes_md` into `render_draft()`
- `tests/test_video_vision.py` — 33 unit tests, no real ffmpeg/yt-dlp/tesseract in CI

## See also

- [`youtube_channel.py`](../../tools/vault_indexer/ingest/youtube_channel.py) — channel poller that invokes this module
- [`../guides/laptop-setup.md`](../guides/laptop-setup.md) — Tesseract install via Homebrew
- [`MULTI_DOMAIN_BRIEFING.md`](../../tools/vault_indexer/MULTI_DOMAIN_BRIEFING.md) — per-indexer scope rules for the shared vault
