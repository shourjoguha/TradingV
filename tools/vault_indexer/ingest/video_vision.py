"""Local video-vision ingest: scene detection + Tesseract OCR → visual notes.

Companion to ``ingest_video.py`` / ``youtube_channel.py``. Adds a "Visual notes"
markdown section to ingested videos by extracting scene-change frames and
running OCR over each. Captures on-screen content the audio transcript misses:
tickers, periodic windows ("1D" / "Weekly"), source attributions ("FRED" /
"TradingView"), key prices, indicator labels.

Domain-agnostic. Drop ``vision: {enabled: true, ...}`` into ANY
``_channel.yaml`` (finance, fitness, nutrition, …) and the same pipeline
runs. No images persist past the ``TemporaryDirectory`` scope. No API spend.

Three-stage frame filter avoids cursor-wiggle / hold-on-same-screen noise:
  1. ffmpeg ``select=gt(scene,T)`` — pixel-change threshold (default 0.10).
  2. ``min_gap_seconds`` (default 10s) — collapse rapid succession; presenters
     hold a screen for the audience to read.
  3. SSIM dedupe (default 0.92) — drop frames whose structural similarity
     with the previous keeper still looks near-identical.

Then capped by ``frame_budget`` (top scene-score wins within budget, sorted
back into time order for stable output).

See ``.claude/modules/video_vision.md`` for the operator-facing description.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Defaults — keep in sync with the YAML schema doc in
# .claude/modules/video_vision.md. Operator overrides per channel via
# the ``vision:`` block in ``_channel.yaml``.
# ---------------------------------------------------------------------------

DEFAULT_SCENE_THRESHOLD = 0.10  # 10% pixel change — rejects cursor wiggle,
                                # catches ticker swaps on the same chart.
DEFAULT_MIN_GAP_SECONDS = 10    # operator: humans hold a chart ≥10s.
DEFAULT_SSIM_THRESHOLD = 0.92   # near-identical drop.
DEFAULT_FRAME_BUDGET = 50
DEFAULT_OCR_LANG = "eng"
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 600  # mirrors audio path in youtube_channel.

# Minimum text quality bar — drop OCR results below this. Three rules
# combined keep "talking head" or "intro animation" frames out of the table.
_OCR_MIN_ALNUM_CHARS = 3
_OCR_MIN_ALNUM_RATIO = 0.30  # ≥30% of non-whitespace chars must be alnum

# Output formatting.
_VISUAL_NOTES_HEADING = "## Visual notes"


@dataclass(frozen=True)
class VisionConfig:
    """Per-channel vision config parsed from ``_channel.yaml``."""

    enabled: bool = False
    frame_budget: int = DEFAULT_FRAME_BUDGET
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD
    min_gap_seconds: int = DEFAULT_MIN_GAP_SECONDS
    ssim_threshold: Optional[float] = DEFAULT_SSIM_THRESHOLD
    ocr_lang: str = DEFAULT_OCR_LANG
    semantic_captions: bool = False  # L3 — not implemented in L2 baseline.

    @classmethod
    def from_mapping(cls, raw: Optional[dict]) -> "VisionConfig":
        if not raw or not isinstance(raw, dict):
            return cls()
        return cls(
            enabled=bool(raw.get("enabled", False)),
            frame_budget=int(raw.get("frame_budget", DEFAULT_FRAME_BUDGET)),
            scene_threshold=float(
                raw.get("scene_threshold", DEFAULT_SCENE_THRESHOLD)
            ),
            min_gap_seconds=int(
                raw.get("min_gap_seconds", DEFAULT_MIN_GAP_SECONDS)
            ),
            ssim_threshold=(
                None if raw.get("ssim_threshold") is None
                else float(raw["ssim_threshold"])
            ),
            ocr_lang=str(raw.get("ocr_lang", DEFAULT_OCR_LANG)),
            semantic_captions=bool(raw.get("semantic_captions", False)),
        )


@dataclass(frozen=True)
class SceneCandidate:
    """A scene-change frame survived all three filter stages."""

    timestamp_seconds: float
    scene_score: float
    frame_path: Path


@dataclass
class VisionResult:
    """Outcome of ``process_video``. Empty markdown when no usable signal."""

    markdown: str = ""
    frame_count: int = 0
    truncated_to_budget: bool = False
    diagnostics: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage 1: ffmpeg scene detect.
# ---------------------------------------------------------------------------

# ffmpeg writes scene metadata to stderr in lines like:
#   [Parsed_metadata_3 @ 0x...] frame:42 pts:12345 pts_time:1.234
#   [Parsed_metadata_3 @ 0x...] lavfi.scene_score=0.156421
# We pair consecutive entries: first capture the pts_time, then the score.
_PTS_TIME_RE = re.compile(r"pts_time:([\d.]+)")
_SCENE_SCORE_RE = re.compile(r"lavfi\.scene_score=([\d.]+)")


def _parse_ffmpeg_scene_stderr(stderr_text: str) -> list[tuple[float, float]]:
    """Extract (timestamp_seconds, scene_score) pairs from ffmpeg stderr.

    Pure function for unit testing. Robust to interleaved log lines.
    """
    pairs: list[tuple[float, float]] = []
    pending_ts: Optional[float] = None
    for line in stderr_text.splitlines():
        ts_m = _PTS_TIME_RE.search(line)
        if ts_m:
            try:
                pending_ts = float(ts_m.group(1))
            except ValueError:
                pending_ts = None
            continue
        sc_m = _SCENE_SCORE_RE.search(line)
        if sc_m and pending_ts is not None:
            try:
                pairs.append((pending_ts, float(sc_m.group(1))))
            except ValueError:
                pass
            pending_ts = None
    return pairs


def _run_ffmpeg_scene_detect(
    video_path: Path,
    *,
    scene_threshold: float,
    out_dir: Path,
) -> list[SceneCandidate]:
    """Run ffmpeg twice: once for scene metadata, once to extract frames.

    Two-pass keeps the parsing simple (metadata in stderr, frames on disk
    via a synced selector). Frames written to ``out_dir/frame_%06d.png``.
    """
    # Pass 1: get (ts, score) pairs.
    meta_cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "info", "-i", str(video_path),
        "-vf", f"select='gt(scene,{scene_threshold})',metadata=print",
        "-vsync", "vfr",
        "-f", "null", "-",
    ]
    try:
        meta = subprocess.run(
            meta_cmd, capture_output=True, text=True, timeout=DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return []
    pairs = _parse_ffmpeg_scene_stderr(meta.stderr or "")
    if not pairs:
        return []

    # Pass 2: extract the frames at those timestamps. Re-running the select
    # filter on the same input produces matching frame_%06d.png files in
    # the same order. Frames numbered 1..N matching pairs.
    out_pattern = out_dir / "frame_%06d.png"
    frame_cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(video_path),
        "-vf", f"select='gt(scene,{scene_threshold})'",
        "-vsync", "vfr",
        "-frames:v", str(len(pairs)),  # safety cap matching pair count
        str(out_pattern),
    ]
    try:
        subprocess.run(
            frame_cmd, check=True, capture_output=True, timeout=DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []

    frames = sorted(out_dir.glob("frame_*.png"))
    out: list[SceneCandidate] = []
    # Pair frames with timestamps. ffmpeg writes them in select-order so
    # zip is correct; tolerate length mismatch defensively.
    for (ts, score), frame_path in zip(pairs, frames):
        out.append(SceneCandidate(timestamp_seconds=ts, scene_score=score, frame_path=frame_path))
    return out


# ---------------------------------------------------------------------------
# Stage 2: time-gap dedupe (operator's "hold-time" intuition).
# ---------------------------------------------------------------------------


def apply_time_gap_dedupe(
    candidates: list[SceneCandidate], *, min_gap_seconds: int
) -> list[SceneCandidate]:
    """Collapse consecutive candidates within ``min_gap_seconds`` — keep first."""
    if min_gap_seconds <= 0:
        return list(candidates)
    out: list[SceneCandidate] = []
    last_kept_ts = -1e9
    for c in candidates:
        if c.timestamp_seconds - last_kept_ts >= min_gap_seconds:
            out.append(c)
            last_kept_ts = c.timestamp_seconds
    return out


# ---------------------------------------------------------------------------
# Stage 3 (optional): SSIM redundancy filter.
# ---------------------------------------------------------------------------


def apply_ssim_dedupe(
    candidates: list[SceneCandidate], *, ssim_threshold: float
) -> list[SceneCandidate]:
    """Drop frames whose SSIM with the previous keeper exceeds threshold.

    Belt-and-suspenders for "presenter briefly tabbed away and came back."
    Gracefully degrades to a no-op when scikit-image isn't installed —
    Stage 2 already catches most duplicates.
    """
    try:
        from skimage.io import imread
        from skimage.metrics import structural_similarity as ssim
    except ImportError:
        return list(candidates)

    if not candidates:
        return []

    survivors: list[SceneCandidate] = [candidates[0]]
    last_img = imread(str(candidates[0].frame_path), as_gray=True)
    for c in candidates[1:]:
        cur_img = imread(str(c.frame_path), as_gray=True)
        try:
            # Resize if dimensions differ (rare, but defensive).
            if cur_img.shape != last_img.shape:
                survivors.append(c)
                last_img = cur_img
                continue
            score = ssim(last_img, cur_img, data_range=1.0)
        except Exception:
            survivors.append(c)
            last_img = cur_img
            continue
        if score < ssim_threshold:
            survivors.append(c)
            last_img = cur_img
    return survivors


# ---------------------------------------------------------------------------
# Stage cap.
# ---------------------------------------------------------------------------


def apply_budget_cap(
    candidates: list[SceneCandidate], *, budget: int
) -> tuple[list[SceneCandidate], bool]:
    """If over budget, keep top scene_score within budget, restore time order."""
    if budget <= 0 or len(candidates) <= budget:
        return list(candidates), False
    top = sorted(candidates, key=lambda c: c.scene_score, reverse=True)[:budget]
    top.sort(key=lambda c: c.timestamp_seconds)
    return top, True


# ---------------------------------------------------------------------------
# Public API: full scene-frame extraction pipeline.
# ---------------------------------------------------------------------------


def extract_scene_frames(
    video_path: Path,
    *,
    out_dir: Path,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
    min_gap_seconds: int = DEFAULT_MIN_GAP_SECONDS,
    ssim_threshold: Optional[float] = DEFAULT_SSIM_THRESHOLD,
    budget: int = DEFAULT_FRAME_BUDGET,
) -> tuple[list[SceneCandidate], bool]:
    """Three-stage scene-cut detection + budget cap. Returns ``(frames, truncated)``."""
    if shutil.which("ffmpeg") is None:
        return [], False
    raw = _run_ffmpeg_scene_detect(
        video_path, scene_threshold=scene_threshold, out_dir=out_dir,
    )
    stage2 = apply_time_gap_dedupe(raw, min_gap_seconds=min_gap_seconds)
    stage3 = (
        apply_ssim_dedupe(stage2, ssim_threshold=ssim_threshold)
        if ssim_threshold is not None
        else stage2
    )
    final, truncated = apply_budget_cap(stage3, budget=budget)
    return final, truncated


# ---------------------------------------------------------------------------
# OCR.
# ---------------------------------------------------------------------------


def _ocr_text_passes_quality(text: str) -> bool:
    """Reject talking-head / intro-animation frames with low text density."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    alnum_chars = sum(1 for c in stripped if c.isalnum())
    if alnum_chars < _OCR_MIN_ALNUM_CHARS:
        return False
    nonspace = sum(1 for c in stripped if not c.isspace())
    if nonspace == 0:
        return False
    if alnum_chars / nonspace < _OCR_MIN_ALNUM_RATIO:
        return False
    return True


def _normalize_ocr_text(text: str) -> str:
    """Collapse whitespace + newlines for a one-line table cell."""
    return " ".join((text or "").split())


def ocr_frame(image_path: Path, *, lang: str = DEFAULT_OCR_LANG) -> str:
    """Tesseract OCR a single frame. Returns "" when content is too noisy.

    Never raises. OCR errors → empty string (skipped in the rendered table).
    """
    if shutil.which("tesseract") is None:
        return ""
    try:
        import pytesseract  # type: ignore[import-untyped]
        from PIL import Image
    except ImportError:
        return ""
    try:
        img = Image.open(image_path)
        raw = pytesseract.image_to_string(img, lang=lang)
    except Exception:
        return ""
    if not _ocr_text_passes_quality(raw):
        return ""
    return _normalize_ocr_text(raw)


# ---------------------------------------------------------------------------
# Markdown rendering.
# ---------------------------------------------------------------------------


def _format_timestamp(seconds: float) -> str:
    """``0:42``, ``2:14``, ``1:23:45``."""
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def render_visual_notes_table(
    rows: list[tuple[float, str]], *, truncated: bool = False
) -> str:
    """Render the ``## Visual notes`` section. Empty input → empty string."""
    filled = [(ts, text) for ts, text in rows if text]
    if not filled:
        return ""
    lines = [_VISUAL_NOTES_HEADING, ""]
    lines.append("| Time | On-screen text |")
    lines.append("|---|---|")
    for ts, text in filled:
        # Escape pipes in cell text to keep table structure intact.
        safe = text.replace("|", "\\|")
        lines.append(f"| {_format_timestamp(ts)} | {safe} |")
    if truncated:
        lines.append("")
        lines.append("_Note: frame count exceeded budget; lower-score frames dropped._")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator.
# ---------------------------------------------------------------------------


def _download_video(url: str, work_dir: Path) -> Optional[Path]:
    """yt-dlp video download into work_dir. Returns the path or None on failure.

    Uses ``[height<=720]`` to cap bandwidth + processing time. 720p is plenty
    for OCR; bigger costs nothing in quality and adds disk + time.
    """
    if shutil.which("yt-dlp") is None:
        return None
    out_template = str(work_dir / "video.%(ext)s")
    cmd = [
        "yt-dlp", "-f", "best[height<=720]/best",
        "-o", out_template,
        url,
    ]
    try:
        subprocess.run(
            cmd, check=True, capture_output=True, timeout=DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    matches = [p for p in work_dir.glob("video.*") if p.is_file()]
    if not matches:
        return None
    # Prefer non-thumbnail/non-info files; biggest by size = the video.
    matches.sort(key=lambda p: p.stat().st_size, reverse=True)
    return matches[0]


def process_video(
    url: str,
    *,
    cfg: VisionConfig,
    work_dir: Optional[Path] = None,
) -> VisionResult:
    """Run the full pipeline. Returns ``VisionResult`` — never raises.

    When ``work_dir`` is None, allocates its own ``TemporaryDirectory`` so
    callers don't have to. When provided, reuses caller's scope.
    """
    if not cfg.enabled:
        return VisionResult(diagnostics={"reason": "vision_disabled"})

    diag: dict = {}

    def _run_in(scope: Path) -> VisionResult:
        video = _download_video(url, scope)
        if video is None:
            return VisionResult(diagnostics={**diag, "reason": "download_failed"})
        frames, truncated = extract_scene_frames(
            video,
            out_dir=scope,
            scene_threshold=cfg.scene_threshold,
            min_gap_seconds=cfg.min_gap_seconds,
            ssim_threshold=cfg.ssim_threshold,
            budget=cfg.frame_budget,
        )
        if not frames:
            return VisionResult(diagnostics={**diag, "reason": "no_scene_frames"})
        rows: list[tuple[float, str]] = []
        for c in frames:
            text = ocr_frame(c.frame_path, lang=cfg.ocr_lang)
            rows.append((c.timestamp_seconds, text))
        markdown = render_visual_notes_table(rows, truncated=truncated)
        kept = sum(1 for _, t in rows if t)
        return VisionResult(
            markdown=markdown,
            frame_count=kept,
            truncated_to_budget=truncated,
            diagnostics={**diag, "raw_frames": len(frames), "kept_ocr_rows": kept},
        )

    if work_dir is not None:
        return _run_in(work_dir)
    with tempfile.TemporaryDirectory() as tmp:
        return _run_in(Path(tmp))


# ---------------------------------------------------------------------------
# CLI entry point (pilot mode).
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Local video-vision pilot. Downloads a video to a tempdir, extracts "
            "scene-change frames, runs OCR on each, prints the resulting "
            "visual-notes markdown table. No images persist past this command."
        )
    )
    ap.add_argument("--url", required=True, help="YouTube/podcast URL (yt-dlp compatible).")
    ap.add_argument(
        "--frame-budget", type=int, default=DEFAULT_FRAME_BUDGET,
        help="Max frames to keep after dedupe. Top scene-score wins within budget.",
    )
    ap.add_argument(
        "--scene-threshold", type=float, default=DEFAULT_SCENE_THRESHOLD,
        help="Pixel-change threshold (0-1). 0.10 = 10%% of pixels changed.",
    )
    ap.add_argument(
        "--min-gap-seconds", type=int, default=DEFAULT_MIN_GAP_SECONDS,
        help="Collapse consecutive scene cuts within this window.",
    )
    ap.add_argument(
        "--ssim-threshold", type=float, default=DEFAULT_SSIM_THRESHOLD,
        help="Drop frames whose SSIM exceeds this with previous keeper. Use -1 to disable.",
    )
    ap.add_argument(
        "--ocr-lang", default=DEFAULT_OCR_LANG,
        help="Tesseract language pack (e.g. 'eng', 'eng+fra').",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print the visual-notes markdown to stdout; do not write any vault file.",
    )
    args = ap.parse_args(argv)

    if shutil.which("yt-dlp") is None and shutil.which("ffmpeg") is None:
        print(
            "missing prereqs: install ffmpeg (brew) and yt-dlp (pip); "
            "see .claude/modules/video_vision.md",
            file=sys.stderr,
        )
        return 1
    if shutil.which("tesseract") is None:
        print(
            "tesseract not on PATH — install via `brew install tesseract`.",
            file=sys.stderr,
        )
        return 1

    cfg = VisionConfig(
        enabled=True,
        frame_budget=args.frame_budget,
        scene_threshold=args.scene_threshold,
        min_gap_seconds=args.min_gap_seconds,
        ssim_threshold=None if args.ssim_threshold < 0 else args.ssim_threshold,
        ocr_lang=args.ocr_lang,
    )
    result = process_video(args.url, cfg=cfg)

    if args.dry_run or True:  # CLI is dry-run by design; vault writes happen via the poller.
        print(result.markdown if result.markdown else "(no visual notes produced)")
        print("---")
        print(f"frames kept: {result.frame_count}, truncated: {result.truncated_to_budget}")
        print(f"diagnostics: {result.diagnostics}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
