"""YouTube channel auto-ingest.

For each `Videos/<channel>/_channel.yaml` whose cadence has elapsed:
  1. Fetch the channel RSS feed (no API key, no quota).
  2. Diff against `seen_video_ids` (rolling window stored in YAML).
  3. For each new video:
       a. Try to pull captions via `yt-dlp --skip-download --write-auto-sub`.
       b. Fall back to whisper transcription on the audio when captions missing.
       c. Render a `<published>-<slug>.md.draft` with `draft: true` frontmatter.
       d. Operator ticks the entry in `_review-queue.md` to promote.
  4. Stamp `last_polled_at` + roll `seen_video_ids`.

Per-channel failure logs and skips; the loop continues to the next channel.
"""
from __future__ import annotations

import datetime
import logging
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import frontmatter

from . import _channel_yaml as _cfg
from .common import slug, write_note
from ..config import CONFIG

logger = logging.getLogger(__name__)


CHANNEL_FILE = _cfg.CHANNEL_FILE
DRAFT_SUFFIX = ".md.draft"


# ---------------------------------------------------------------------------
# RSS feed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeedEntry:
    video_id: str
    title: str
    published_at: str          # ISO date (YYYY-MM-DD)
    url: str


def _channel_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def resolve_channel_id(channel_url: str) -> Optional[str]:
    """Best-effort: ask yt-dlp to print the channel_id of any video on the
    channel. Used when operator dropped a `_channel.yaml` with only a
    `channel_url`. Returns None on any failure (logged)."""
    try:
        proc = subprocess.run(
            ["yt-dlp", "--print", "%(channel_id)s",
             "--playlist-items", "1",
             "--quiet", "--no-warnings", "--ignore-errors",
             channel_url],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("yt-dlp resolve_channel_id failed for %s: %s", channel_url, e)
        return None
    out = (proc.stdout or "").strip().splitlines()
    for line in out:
        line = line.strip()
        if line.startswith("UC") and len(line) >= 20:
            return line
    return None


def fetch_feed(channel_id: str) -> list[FeedEntry]:
    """Return entries newest-first. Empty list on any fetch error (logged)."""
    try:
        import feedparser
    except ImportError:                              # pragma: no cover
        logger.warning("feedparser not installed; skipping channel %s", channel_id)
        return []
    parsed = feedparser.parse(_channel_feed_url(channel_id))
    out: list[FeedEntry] = []
    for e in (parsed.entries or []):
        vid = e.get("yt_videoid") or _extract_video_id(e.get("id", ""))
        if not vid:
            continue
        published = (e.get("published") or e.get("pubDate") or "")[:10] or None
        if not published:
            continue
        out.append(FeedEntry(
            video_id=vid,
            title=e.get("title", "(untitled)"),
            published_at=published,
            url=e.get("link", f"https://www.youtube.com/watch?v={vid}"),
        ))
    return out


def _extract_video_id(s: str) -> Optional[str]:
    m = re.search(r"yt:video:([\w-]+)", s)
    if m:
        return m.group(1)
    m = re.search(r"v=([\w-]+)", s)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Captions / whisper transcription
# ---------------------------------------------------------------------------


def fetch_captions(url: str, *, work_dir: Path) -> Optional[str]:
    """Pull English auto-subtitles via yt-dlp without downloading audio.
    Returns the cleaned transcript string, or None when no captions exist."""
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-sub",
        "--sub-lang", "en",
        "--sub-format", "vtt",
        "-o", str(work_dir / "%(id)s"),
        url,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning("yt-dlp captions fetch failed for %s: %s", url, e)
        return None
    vtt_files = list(work_dir.glob("*.en.vtt"))
    if not vtt_files:
        return None
    return _vtt_to_text(vtt_files[0].read_text(encoding="utf-8"))


def _vtt_to_text(vtt: str) -> str:
    """Strip VTT timestamps + cue identifiers; collapse whitespace."""
    lines = []
    for raw in vtt.splitlines():
        s = raw.strip()
        if not s or s == "WEBVTT":
            continue
        if "-->" in s:
            continue
        if s.isdigit():
            continue
        # Strip inline timestamp tags like <00:00:01.000>
        s = re.sub(r"<\d\d:\d\d:\d\d\.\d{3}>", "", s)
        s = re.sub(r"<[^>]+>", "", s)
        lines.append(s)
    # Dedupe consecutive duplicate lines (auto-captions repeat each line).
    out: list[str] = []
    for line in lines:
        if not out or out[-1] != line:
            out.append(line)
    return "\n".join(out).strip()


def whisper_transcribe(url: str, *, work_dir: Path, model: str = "small") -> Optional[str]:
    """Download audio via yt-dlp + run whisper. Heavy; only used when captions
    are absent. Returns the transcript or None on failure."""
    out_template = str(work_dir / "audio.%(ext)s")
    dl = [
        "yt-dlp", "-x", "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", out_template,
        url,
    ]
    try:
        subprocess.run(dl, check=True, capture_output=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning("yt-dlp audio download failed for %s: %s", url, e)
        return None
    audio_files = [p for p in work_dir.glob("audio.*") if p.is_file()]
    if not audio_files:
        return None
    try:
        import whisper                                # lazy: heavy import
        m = whisper.load_model(model)
        result = m.transcribe(str(audio_files[0]))
        return (result.get("text") or "").strip()
    except Exception as e:                            # noqa: BLE001
        logger.warning("whisper transcription failed for %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Draft rendering + write
# ---------------------------------------------------------------------------


def render_draft(
    *,
    entry: FeedEntry,
    transcript: str,
    cfg: dict[str, Any],
    transcript_source: str,             # 'captions' | 'whisper'
) -> tuple[str, dict[str, Any]]:
    """Return (body_md, metadata_dict) for the draft note."""
    author = cfg.get("author") or "(unknown)"
    body_lines = [
        f"# {entry.title}",
        "",
        f"*{author} · {entry.published_at} · [Watch]({entry.url})*",
        "",
        "## Transcript",
        f"_(source: {transcript_source})_",
        "",
        transcript or "_(empty)_",
    ]
    metadata = {
        "kind": cfg.get("default_kind", "video"),
        "title": entry.title,
        "author": author,
        "source_url": entry.url,
        "video_id": entry.video_id,
        "published_at": entry.published_at,
        "horizon_months": cfg.get("default_horizon_months", 6),
        "parent": _parent_index_for(cfg),
        "tags": list(cfg.get("default_tags") or []),
        "asr": transcript_source,
        "draft": True,
    }
    return "\n".join(body_lines), metadata


def _parent_index_for(cfg: dict[str, Any]) -> Optional[str]:
    """Best-effort guess at the channel's `_index.md`. Falls back to None
    when the operator hasn't authored one yet."""
    rel = cfg.get("_rel_dir")               # injected by ingest_one()
    if not rel:
        return None
    return f"{rel}/_index.md"


def write_draft(
    *,
    vault_root: Path,
    rel_dir: str,
    entry: FeedEntry,
    body: str,
    metadata: dict[str, Any],
) -> Path:
    """Write `<rel_dir>/<published>-<slug>.md.draft`. Returns abs path.
    Idempotent: if the draft already exists for this video_id, no-op."""
    target_dir = vault_root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{entry.published_at}-{slug(entry.title)}{DRAFT_SUFFIX}"
    target = target_dir / filename
    if target.exists():
        return target
    metadata = {**metadata, "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    post = frontmatter.Post(content=body, **metadata)
    target.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Per-channel orchestration
# ---------------------------------------------------------------------------


def ingest_one(
    *,
    channel_dir: Path,
    vault_root: Path,
    max_videos_per_run: int = 3,
) -> dict[str, Any]:
    """Poll one channel. Returns {fetched, drafts_written, skipped}.
    Best-effort — exceptions are caught + logged."""
    cfg = _cfg.load(channel_dir)
    if cfg is None:
        return {"reason": "no_yaml", "drafts_written": 0}
    if not _cfg.is_due(cfg):
        return {"reason": "not_due", "drafts_written": 0}

    rel_dir = str(channel_dir.relative_to(vault_root))
    cfg = {**cfg, "_rel_dir": rel_dir}              # ephemeral; not saved

    channel_id = cfg.get("channel_id")
    placeholder = isinstance(channel_id, str) and channel_id.startswith("TODO")
    if not channel_id or placeholder:
        url = cfg.get("channel_url")
        if not url:
            logger.warning("channel %s has no channel_id or channel_url; skipping", channel_dir)
            return {"reason": "no_channel_id", "drafts_written": 0}
        resolved = resolve_channel_id(url)
        if not resolved:
            logger.warning("channel %s: failed to resolve channel_id from %s", channel_dir, url)
            return {"reason": "resolve_failed", "channel_url": url, "drafts_written": 0}
        logger.info("channel %s: resolved channel_id %s from %s", channel_dir, resolved, url)
        channel_id = resolved
        # Persist back so subsequent ticks skip the resolve step.
        on_disk = {k: v for k, v in cfg.items() if not k.startswith("_")}
        on_disk["channel_id"] = resolved
        _cfg.save(channel_dir, on_disk)
        cfg = {**cfg, "channel_id": resolved}

    entries = fetch_feed(channel_id)
    new_entries = [e for e in entries if not _cfg.has_seen(cfg, e.video_id)]
    new_entries = new_entries[:max_videos_per_run]   # cap per-tick load

    drafts_written = 0
    fetched_ids: list[str] = []

    for entry in new_entries:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            transcript: Optional[str] = None
            source = "captions"
            if cfg.get("ingest", {}).get("prefer_captions", True):
                transcript = fetch_captions(entry.url, work_dir=tmp_path)
            if not transcript:
                source = "whisper"
                transcript = whisper_transcribe(entry.url, work_dir=tmp_path)
            if not transcript:
                logger.warning(
                    "no transcript for %s (%s); skipping draft",
                    entry.title, entry.url,
                )
                fetched_ids.append(entry.video_id)
                continue
        body, metadata = render_draft(
            entry=entry,
            transcript=transcript,
            cfg=cfg,
            transcript_source=source,
        )
        write_draft(
            vault_root=vault_root,
            rel_dir=rel_dir,
            entry=entry,
            body=body,
            metadata=metadata,
        )
        drafts_written += 1
        fetched_ids.append(entry.video_id)

    # Persist polled state (drop the ephemeral _rel_dir).
    cfg.pop("_rel_dir", None)
    cfg = _cfg.mark_polled(cfg, video_ids=fetched_ids)
    _cfg.save(channel_dir, cfg)

    return {
        "channel": channel_id,
        "fetched": len(new_entries),
        "drafts_written": drafts_written,
        "skipped_no_transcript": len(new_entries) - drafts_written,
    }


def discover_channel_dirs(vault_root: Path) -> Iterable[Path]:
    """Yield every directory under <vault>/Videos/ that has a _channel.yaml."""
    videos_root = vault_root / "Videos"
    if not videos_root.exists():
        return []
    return [p.parent for p in videos_root.rglob(CHANNEL_FILE) if p.is_file()]


def ingest_all(*, vault_root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Top-level orchestrator — discover + ingest every channel that's due."""
    root = vault_root or CONFIG.vault_path
    out: list[dict[str, Any]] = []
    for channel_dir in discover_channel_dirs(root):
        try:
            result = ingest_one(channel_dir=channel_dir, vault_root=root)
            out.append({"channel_dir": str(channel_dir.relative_to(root)), **result})
        except Exception as e:                       # noqa: BLE001
            logger.exception("ingest_one failed for %s", channel_dir)
            out.append({
                "channel_dir": str(channel_dir.relative_to(root)),
                "error": str(e),
            })
    return out


# ---------------------------------------------------------------------------
# Manual CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Poll all _channel.yaml under Videos/")
    ap.add_argument("--vault", default=str(CONFIG.vault_path))
    args = ap.parse_args()
    results = ingest_all(vault_root=Path(args.vault))
    for r in results:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
