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

## Upgrade path to L3 (Moondream2)

`vision.semantic_captions: true` is reserved for a future L3 path where each frame also gets a 1-line semantic caption from a local Moondream2 VLM (~2GB model weights, ~2s/frame on M3 CPU). Not implemented in L2 baseline. Triggers to revisit:
- L2 (OCR alone) produces too much noise on a key channel
- Operator wants chart-pattern reasoning ("descending wedge", "double top") that OCR can't surface

## Files

- `tools/vault_indexer/ingest/video_vision.py` — pipeline + CLI
- `tools/vault_indexer/ingest/youtube_channel.py` — `ingest_one()` reads `cfg.vision`, calls `video_vision.process_video()` inside the existing temp-dir scope, threads `visual_notes_md` into `render_draft()`
- `tests/test_video_vision.py` — 33 unit tests, no real ffmpeg/yt-dlp/tesseract in CI

## See also

- [`youtube_channel.py`](../../tools/vault_indexer/ingest/youtube_channel.py) — channel poller that invokes this module
- [`../guides/laptop-setup.md`](../guides/laptop-setup.md) — Tesseract install via Homebrew
- [`MULTI_DOMAIN_BRIEFING.md`](../../tools/vault_indexer/MULTI_DOMAIN_BRIEFING.md) — per-indexer scope rules for the shared vault
