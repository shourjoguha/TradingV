"""Queue-driven YouTube ingest.

Reads ``<vault>/<queue-rel-path>`` for unchecked URL lines, ingests each via
``download_audio + transcribe + write_note``, and updates the queue file
atomically:

  - On success: tick the line ``[x]`` and append ``✓ <ts> → <output>``.
  - On failure (under retry cap): keep the line unchecked, increment
    ``attempts=N`` metadata, append an inline ``<!-- failed: ... -->`` comment.
  - On failure (at retry cap): move the line into a ``## Quarantined`` section
    with a consolidated reason. No further retries until the operator moves
    it back to ``## Queue``.

A non-blocking ``fcntl.flock`` is held on the queue file so concurrent runs
of the same ingester for the same queue silently exit. Different queue files
(fitness vs nutrition) can run concurrently.

Designed to be invoked by launchd / cron on a schedule.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .common import iso_week, slug, write_note
from .ingest_video import download_audio, transcribe
from ..config import CONFIG


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"}


_TODO_RE = re.compile(r"^\s*- \[ \]\s+(.*\S)\s*$")
_DONE_RE = re.compile(r"^\s*- \[[xX]\]\s+(.*\S)\s*$")
_KV_RE = re.compile(r'(\w+)=("[^"]*"|\S+)')
_URL_RE = re.compile(r"https?://\S+")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")

# Section markers used by the queue file format.
_SECTION_QUEUE = "queue"
_SECTION_DONE = "done"
_SECTION_QUARANTINED = "quarantined"
# Anything else we treat as 'queue' (legacy queue files have no headings or use
# arbitrary headings before the queue section).


@dataclass
class QueueEntry:
    line_idx: int
    raw: str
    url: str
    author: Optional[str]
    horizon: int
    model: str
    title: Optional[str]
    published: Optional[str]
    attempts: int = 0


def _parse_kv(rest: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in _KV_RE.findall(rest):
        out[k] = v.strip('"')
    return out


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _section_for_heading(heading_text: str) -> str:
    """Map a heading like 'Quarantined' or 'Done' to a canonical section key."""
    h = heading_text.strip().lower()
    if "quarant" in h:
        return _SECTION_QUARANTINED
    if h.startswith("done"):
        return _SECTION_DONE
    if h.startswith("queue"):
        return _SECTION_QUEUE
    return _SECTION_QUEUE      # default: pre-section content is queue


def _parse_queue(text: str, *, default_horizon: int, default_model: str) -> list[QueueEntry]:
    """Yield only entries in the active queue section. Skips Done + Quarantined."""
    entries: list[QueueEntry] = []
    section = _SECTION_QUEUE       # default for lines before any heading
    for i, line in enumerate(text.splitlines()):
        m_h = _HEADING_RE.match(line)
        if m_h:
            section = _section_for_heading(m_h.group(1))
            continue
        if section != _SECTION_QUEUE:
            continue
        m = _TODO_RE.match(line)
        if not m:
            continue
        rest = m.group(1)
        url_match = _URL_RE.search(rest)
        if not url_match:
            continue
        url = url_match.group(0).rstrip("|").strip()
        kv = _parse_kv(rest)
        author = kv.get("author")
        horizon = int(kv["horizon"]) if kv.get("horizon", "").isdigit() else default_horizon
        model = kv.get("model", default_model)
        attempts = int(kv["attempts"]) if kv.get("attempts", "").isdigit() else 0
        entries.append(QueueEntry(
            line_idx=i,
            raw=line,
            url=url,
            author=slug(author) if author else None,
            horizon=horizon,
            model=model,
            title=kv.get("title"),
            published=kv.get("published"),
            attempts=attempts,
        ))
    return entries


def _video_id_from_url(url: str) -> Optional[str]:
    """Extract YouTube video ID from a URL's ``v=`` query param."""
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return qs.get("v", [None])[0]
    except Exception:                                          # noqa: BLE001
        return None


def _probe_youtube_metadata(url: str, timeout: int = 15) -> tuple[Optional[str], Optional[str]]:
    """Probe yt-dlp for uploader slug + video title without downloading.

    Returns ``(author_slug, title)`` — either may be None if probe fails.
    Uses ``--no-playlist`` so playlist URLs don't expand.
    """
    cmd = [
        "yt-dlp", "--skip-download", "--no-warnings", "--no-playlist",
        "--print", "%(uploader_id)s|%(uploader)s|%(channel)s|%(title)s",
        url,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=True,
        )
    except Exception:                                          # noqa: BLE001
        return None, None
    line = (result.stdout or "").strip().splitlines()[0] if result.stdout else ""
    parts = line.split("|")
    author: Optional[str] = None
    for field in parts[:3]:
        field = field.strip()
        if field and field.upper() != "NA":
            author = slug(field)
            break
    title: Optional[str] = None
    if len(parts) >= 4:
        raw_title = "|".join(parts[3:]).strip()   # rejoin in case title contains '|'
        if raw_title and raw_title.upper() != "NA":
            title = raw_title
    return author, title


def _url_kind(url: str) -> str:
    """Return 'youtube' for any YouTube host, 'article' otherwise."""
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:                                       # noqa: BLE001
        return "article"
    return "youtube" if host.lower() in YOUTUBE_HOSTS else "article"


def _defuddle_extract(url: str, timeout: int = 60) -> dict:
    """Call defuddle CLI to extract clean markdown + metadata from a URL.

    Uses ``npx --yes defuddle parse <url> --json`` so no global install needed.
    Returns the parsed JSON dict (with `title`, `author`, `published`,
    `contentMarkdown`, `domain`, `wordCount`, ...). Raises on failure.
    """
    cmd = ["npx", "--yes", "defuddle", "parse", url, "--json"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"defuddle exit {e.returncode}: {e.stderr[:200]}") from e
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"defuddle timed out after {timeout}s")
    # Strip Node experimental warnings prefix if any.
    out = result.stdout.lstrip()
    if out.startswith("("):                                  # warning lines
        # Find first '{' and trim
        i = out.find("{")
        if i >= 0:
            out = out[i:]
    try:
        return json.loads(out)
    except Exception as e:                                   # noqa: BLE001
        raise RuntimeError(f"defuddle returned invalid json: {e}") from e


def _ingest_video(entry: QueueEntry, *, vault_root: Path, rel_dir_prefix: str) -> str:
    """Video pipeline: yt-dlp + Whisper. Returns relative output path."""
    published = entry.published or datetime.date.today().isoformat()
    # Probe metadata from yt-dlp when author or title not explicitly supplied.
    probed_author: Optional[str] = None
    probed_title: Optional[str] = None
    if not entry.author or not entry.title:
        probed_author, probed_title = _probe_youtube_metadata(entry.url)
    author = entry.author or probed_author or "_unsorted"
    # Title priority: explicit > yt-dlp video title > video ID > generic fallback.
    title = entry.title or probed_title or _video_id_from_url(entry.url) or f"{author}-{iso_week()}"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        audio = download_audio(entry.url, tmp_path)
        _, body = transcribe(audio, entry.model)
    if not body or not body.strip():
        raise RuntimeError(
            "whisper returned empty transcript (model load or inference failure — "
            "check stderr for HuggingFace 401 / model repo / disk-space)"
        )
    week = iso_week(datetime.date.fromisoformat(published))
    rel_dir = f"{rel_dir_prefix.rstrip('/')}/{author}"
    filename = f"{week}-{slug(title)}.md"
    target = write_note(
        vault_root=vault_root,
        rel_dir=rel_dir,
        filename=filename,
        body=f"# {title}\n\n[Source]({entry.url})\n\n{body}",
        metadata={
            "kind": "video",
            "title": title,
            "author": author,
            "source_url": entry.url,
            "published_at": published,
            "horizon_months": entry.horizon,
            "asr": "whisper",
            "whisper_model": entry.model,
            "tags": [],
        },
    )
    return str(target.relative_to(vault_root))


def _ingest_article(entry: QueueEntry, *, vault_root: Path, rel_dir_prefix: str) -> str:
    """Article pipeline: defuddle clean-extract + write_note. Returns relative path.

    `rel_dir_prefix` should be ``Newsletters/<domain>`` (or similar). The
    operator-supplied ``author`` slug becomes the folder name; the article's
    own author (from defuddle) lands in frontmatter as ``source_author``.
    """
    parsed = _defuddle_extract(entry.url)
    md_body = parsed.get("contentMarkdown") or parsed.get("content") or ""
    if not md_body.strip():
        raise RuntimeError("defuddle returned empty content (paywall? login wall?)")

    # Author: operator slug > defuddle-detected > _unsorted.
    author = entry.author or (slug(parsed.get("author")) if parsed.get("author") else None) or "_unsorted"
    # Title: queue-line override > defuddle title > generic.
    title = entry.title or parsed.get("title") or f"{author}-{iso_week()}"
    # Published: queue-line > defuddle (ISO date) > today.
    pub_raw = entry.published or parsed.get("published") or datetime.date.today().isoformat()
    try:
        published = pub_raw[:10]                                # YYYY-MM-DD slice
        datetime.date.fromisoformat(published)
    except Exception:                                          # noqa: BLE001
        published = datetime.date.today().isoformat()

    week = iso_week(datetime.date.fromisoformat(published))
    rel_dir = f"{rel_dir_prefix.rstrip('/')}/{author}"
    filename = f"{week}-{slug(title)}.md"
    target = write_note(
        vault_root=vault_root,
        rel_dir=rel_dir,
        filename=filename,
        body=f"# {title}\n\n[Source]({entry.url})\n\n{md_body}",
        metadata={
            "kind": "article",
            "title": title,
            "author": author,                                   # operator-chosen or fallback slug
            "source_author": parsed.get("author"),              # defuddle-detected
            "source_site": parsed.get("site") or parsed.get("domain"),
            "source_url": entry.url,
            "published_at": published,
            "horizon_months": entry.horizon,
            "extractor": "defuddle",
            "word_count": parsed.get("wordCount"),
            "tags": [],
        },
    )
    return str(target.relative_to(vault_root))


def _ingest_one(entry: QueueEntry, *, vault_root: Path, rel_dir_video: str, rel_dir_article: Optional[str]) -> str:
    """Dispatch by URL kind. Returns relative output path."""
    kind = _url_kind(entry.url)
    if kind == "youtube":
        return _ingest_video(entry, vault_root=vault_root, rel_dir_prefix=rel_dir_video)
    # article path
    if not rel_dir_article:
        raise RuntimeError(
            f"non-YouTube URL but --rel-dir-article not configured: {entry.url}"
        )
    return _ingest_article(entry, vault_root=vault_root, rel_dir_prefix=rel_dir_article)


def _bump_attempts_in_line(line: str, new_attempts: int) -> str:
    """Replace `attempts=N` in the line, or append `| attempts=N` if absent."""
    if " attempts=" in line or "|attempts=" in line:
        return re.sub(r"attempts=\d+", f"attempts={new_attempts}", line)
    # Append after the URL line. Conservative: just append to end with ` | attempts=N`.
    return f"{line.rstrip()} | attempts={new_attempts}"


def _rewrite_queue(
    queue_path: Path,
    original_lines: list[str],
    *,
    updates: Optional[dict[int, str]] = None,
    failure_comments: Optional[dict[int, str]] = None,
    removals: Optional[set[int]] = None,
    quarantine_appends: Optional[list[str]] = None,
    done_appends: Optional[list[str]] = None,
) -> None:
    """Atomically rewrite the queue file.

    - ``updates``: line_idx → new content (in-place line replacement).
    - ``failure_comments``: line_idx → reason; appended after line as HTML comment.
    - ``removals``: line indices to drop entirely (used when promoting to quarantine or done).
    - ``quarantine_appends``: lines to insert under the ``## Quarantined`` section
      (created if missing, before the ``## Done`` section if present).
    - ``done_appends``: lines to insert under the ``## Done`` section
      (created if missing, appended at end).
    """
    updates = updates or {}
    failure_comments = failure_comments or {}
    removals = removals or set()
    quarantine_appends = quarantine_appends or []
    done_appends = done_appends or []

    out: list[str] = []
    for i, line in enumerate(original_lines):
        if i in removals:
            continue
        if i in updates:
            out.append(updates[i])
        else:
            out.append(line)
        if i in failure_comments:
            out.append(f"  <!-- failed: {failure_comments[i]} at {_now_iso()} -->")

    if quarantine_appends:
        out = _insert_into_quarantine_section(out, quarantine_appends)
    if done_appends:
        out = _insert_into_done_section(out, done_appends)

    new_text = "\n".join(out)
    if not new_text.endswith("\n"):
        new_text += "\n"
    tmp_path = queue_path.with_suffix(queue_path.suffix + ".tmp")
    tmp_path.write_text(new_text, encoding="utf-8")
    os.replace(tmp_path, queue_path)


def _insert_into_quarantine_section(lines: list[str], to_append: list[str]) -> list[str]:
    """Place ``to_append`` under ``## Quarantined``. Create the section if missing.

    Strategy:
      1. If ``## Quarantined`` heading exists → insert lines immediately after
         the heading (and any blank line that follows it).
      2. Else → append a new ``## Quarantined`` section before ``## Done`` if
         present, else at end.
    """
    quarantine_idx = None
    done_idx = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        h = _section_for_heading(m.group(1))
        if h == _SECTION_QUARANTINED and quarantine_idx is None:
            quarantine_idx = i
        elif h == _SECTION_DONE and done_idx is None:
            done_idx = i

    if quarantine_idx is not None:
        # Skip past trailing blank line if present.
        insert_at = quarantine_idx + 1
        if insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        return lines[:insert_at] + to_append + lines[insert_at:]

    # Section doesn't exist — create it.
    new_section = ["", "## Quarantined", "", *to_append, ""]
    if done_idx is not None:
        return lines[:done_idx] + new_section + lines[done_idx:]
    return [*lines, *new_section]


def _insert_into_done_section(lines: list[str], to_append: list[str]) -> list[str]:
    """Place ``to_append`` under ``## Done``. Create the section if missing.

    Strategy:
      1. If ``## Done`` heading exists → insert lines immediately after the
         heading (and any blank line that follows it).
      2. Else → append a new ``## Done`` section at end of file.
    """
    done_idx = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        if _section_for_heading(m.group(1)) == _SECTION_DONE:
            done_idx = i
            break

    if done_idx is not None:
        insert_at = done_idx + 1
        if insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        return lines[:insert_at] + to_append + lines[insert_at:]

    # Section doesn't exist — create it at end of file.
    new_section = ["", "## Done", "", *to_append, ""]
    return [*lines, *new_section]


def _ping_reload(reload_url: str, timeout: float = 300.0) -> Optional[str]:
    req = urllib.request.Request(reload_url, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:                              # noqa: BLE001
        return f"reload failed: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True,
                    help="Queue file path relative to vault root, "
                         "e.g. Videos/fitness/_ingest_queue.md")
    ap.add_argument("--rel-dir-prefix", "--rel-dir-video", dest="rel_dir_video", required=True,
                    help="Where ingested videos land, e.g. Videos/fitness. "
                         "(--rel-dir-prefix kept for back-compat.)")
    ap.add_argument("--rel-dir-article", default=None,
                    help="Where ingested articles land, e.g. Newsletters/fitness. "
                         "Required only if the queue contains non-YouTube URLs.")
    ap.add_argument("--reload-url", default=None,
                    help="If set, POST here after batch to refresh the indexer cache.")
    ap.add_argument("--reload-timeout", type=float, default=300.0,
                    help="Seconds to wait on the reload POST. Default 300 — the "
                         "on-demand indexer may cold-start (model load) when "
                         "socket-activated by this ping.")
    ap.add_argument("--default-horizon", type=int, default=12)
    ap.add_argument("--default-model", default="small",
                    choices=("tiny", "base", "small", "medium", "large", "large-v3"))
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="After this many failed attempts, move the URL to "
                         "## Quarantined and stop retrying.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse queue and print plan; don't ingest or rewrite.")
    args = ap.parse_args()

    # Tool checks: yt-dlp + ffmpeg always (videos can appear). npx only if articles
    # are possible (i.e. --rel-dir-article was set).
    if shutil.which("yt-dlp") is None:
        print("yt-dlp not on PATH", file=sys.stderr)
        return 1
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not on PATH", file=sys.stderr)
        return 1
    if args.rel_dir_article and shutil.which("npx") is None:
        print("npx not on PATH (Node.js needed for defuddle article extraction)", file=sys.stderr)
        return 1

    queue_path = CONFIG.vault_path / args.queue
    if not queue_path.exists():
        print(f"queue file not found: {queue_path}", file=sys.stderr)
        return 1

    # Non-blocking flock — exit silently if another run is in progress.
    lock = open(queue_path, "rb")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another ingest run is active; exiting", file=sys.stderr)
        return 0

    try:
        text = queue_path.read_text(encoding="utf-8")
        original_lines = text.splitlines()
        entries = _parse_queue(
            text, default_horizon=args.default_horizon, default_model=args.default_model,
        )
        if args.dry_run:
            print(json.dumps([e.__dict__ for e in entries], indent=2))
            return 0

        updates: dict[int, str] = {}
        failure_comments: dict[int, str] = {}
        removals: set[int] = set()
        quarantine_appends: list[str] = []
        done_appends: list[str] = []
        ingested: list[str] = []

        for entry in entries:
            try:
                rel = _ingest_one(
                    entry, vault_root=CONFIG.vault_path,
                    rel_dir_video=args.rel_dir_video,
                    rel_dir_article=args.rel_dir_article,
                )
                # Move successful line out of ## Queue and into ## Done.
                removals.add(entry.line_idx)
                done_appends.append(
                    f"- [x] {entry.url} ✓ {_now_iso()} → {rel}"
                )
                ingested.append(rel)
                print(f"ingested → {rel}")
            except Exception as e:                      # noqa: BLE001
                msg = str(e).replace("\n", " ")[:200]
                new_attempts = entry.attempts + 1
                if new_attempts >= args.max_attempts:
                    # Quarantine: drop the original line, append to quarantine section.
                    removals.add(entry.line_idx)
                    author_field = f" | author={entry.author}" if entry.author else ""
                    consolidated = (
                        f"- [ ] {entry.url}{author_field} | "
                        f"quarantined_at={_now_iso()} | "
                        f"attempts={new_attempts} | "
                        f'last_error="{msg[:120]}"'
                    )
                    quarantine_appends.append(consolidated)
                    print(
                        f"quarantined (after {new_attempts} attempts): {entry.url} — {msg}",
                        file=sys.stderr,
                    )
                else:
                    # Retry next run: bump attempts in the line + add comment.
                    updates[entry.line_idx] = _bump_attempts_in_line(
                        entry.raw, new_attempts
                    )
                    failure_comments[entry.line_idx] = (
                        f"attempt {new_attempts}/{args.max_attempts} — {msg}"
                    )
                    print(
                        f"failed ({new_attempts}/{args.max_attempts}): {entry.url} — {msg}",
                        file=sys.stderr,
                    )

        if updates or failure_comments or removals or quarantine_appends or done_appends:
            _rewrite_queue(
                queue_path, original_lines,
                updates=updates,
                failure_comments=failure_comments,
                removals=removals,
                quarantine_appends=quarantine_appends,
                done_appends=done_appends,
            )

        if ingested and args.reload_url:
            result = _ping_reload(args.reload_url, timeout=args.reload_timeout)
            print(f"reload: {result}")

        had_failures = bool(failure_comments) or bool(quarantine_appends)
        return 0 if not had_failures else 2
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
