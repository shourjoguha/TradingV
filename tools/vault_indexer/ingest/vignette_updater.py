"""Auto-enrich channel ``_index.md`` with a rolling chart-references table.

Operator-authored content above and below the sentinel-bounded block is
preserved. Idempotent — same video_id ingested twice produces the same
output. FIFO eviction at ``rollup_cap``.

The vault-indexer's ``/folder-context`` endpoint returns ``_index.md``
verbatim, so research bundles + hypothesis stress-tests automatically
pick up the rolled-up signal without further wiring.

Used by ``youtube_channel.py:ingest_one()`` after a successful draft
when ``cfg.vision.chart_extraction.enabled`` is True.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


SENTINEL_START = "<!-- AUTO:chart-references:start -->"
SENTINEL_END = "<!-- AUTO:chart-references:end -->"

# Compiled once. Captures the entire sentinel-bounded region (greedy across
# newlines) so we can replace it atomically with a fresh rendering.
_BLOCK_RE = re.compile(
    re.escape(SENTINEL_START) + r"(.*?)" + re.escape(SENTINEL_END),
    re.DOTALL,
)


def render_block(entries: list[dict]) -> str:
    """Render the sentinel-bounded block from a list of entry dicts.

    Each entry is shaped like:
        {
          "video_id": "abc123",
          "published_at": "2026-05-14",
          "title": "...",
          "rel_path": "Videos/click-capital/2026-W19-foo.md",
          "summary": "SMR (4H candle), NASDAQ (line)"
        }

    Caller controls FIFO eviction by passing a list capped at rollup_cap.
    """
    if not entries:
        # Still render the markers so the block exists for future upserts —
        # but with an explanatory placeholder.
        body = (
            "_No chart references captured yet. Auto-generated; "
            "operator-edited content above and below this block is preserved._"
        )
        return f"{SENTINEL_START}\n{body}\n{SENTINEL_END}"

    lines = [
        SENTINEL_START,
        "## Recent chart references (auto-generated)",
        "",
        "| Date | Video | Charts |",
        "|---|---|---|",
    ]
    for e in entries:
        date = e.get("published_at", "")
        title = (e.get("title", "") or "").replace("|", "\\|")
        rel = e.get("rel_path", "")
        summary = (e.get("summary", "") or "").replace("|", "\\|")
        # Markdown link to the video note when rel path provided.
        title_cell = f"[{title}]({rel})" if rel and title else (title or rel)
        lines.append(f"| {date} | {title_cell} | {summary} |")
    lines.append("")
    lines.append(
        "_Auto-generated; operator-edited content above and below this block "
        "is preserved. Edit channel notes elsewhere on the page._"
    )
    lines.append(SENTINEL_END)
    return "\n".join(lines)


def _read_existing_entries(content: str) -> list[dict]:
    """Best-effort parse of existing entries inside the sentinel block so
    we can dedupe by video_id and FIFO-evict. Falls back to empty list
    when the block doesn't parse — caller's new entry then becomes the
    only entry.

    Format expected: markdown table with columns
        | YYYY-MM-DD | [title](rel_path) | summary |
    """
    match = _BLOCK_RE.search(content)
    if not match:
        return []
    inner = match.group(1)
    entries: list[dict] = []
    row_re = re.compile(
        r"^\s*\|\s*"
        r"(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*"
        r"(?P<title>.+?)\s*\|\s*"
        r"(?P<summary>.*?)\s*\|\s*$",
        re.MULTILINE,
    )
    link_re = re.compile(r"^\[(?P<title>.+?)\]\((?P<rel>.+?)\)$")
    for m in row_re.finditer(inner):
        date = m.group("date")
        raw_title = m.group("title").strip()
        summary = m.group("summary").strip()
        title = raw_title
        rel = ""
        link_m = link_re.match(raw_title)
        if link_m:
            title = link_m.group("title")
            rel = link_m.group("rel")
        # video_id key: best-effort from the rel path (filename stem).
        video_id = ""
        if rel:
            video_id = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        entries.append({
            "video_id": video_id,
            "published_at": date,
            "title": title,
            "rel_path": rel,
            "summary": summary,
        })
    return entries


def _dedupe_and_sort(
    entries: list[dict], new_entry: dict, *, cap: int
) -> list[dict]:
    """Insert new entry, dedupe by rel_path (resilient to round-trip),
    sort newest first, cap.

    Using rel_path as the dedupe key (not video_id) because the markdown
    parser can't reliably recover the operator's video_id from the
    rendered row — it can only see the link target. rel_path uniquely
    identifies a video in the vault, so this is the stable key.
    """
    new_rel = new_entry.get("rel_path", "")
    merged = [e for e in entries if e.get("rel_path", "") != new_rel] if new_rel else list(entries)
    merged.insert(0, new_entry)
    # Sort by published_at desc (stable). Lexicographic works because ISO dates.
    merged.sort(key=lambda e: e.get("published_at", ""), reverse=True)
    if cap > 0 and len(merged) > cap:
        merged = merged[:cap]
    return merged


def summarise_chart_references(refs: list[dict]) -> str:
    """One-line summary suitable for the channel _index.md "Charts" column.

    Aggregates per-frame structured refs into a compact human-readable
    string. Empty input → empty string.
    """
    if not refs:
        return ""
    parts: list[str] = []
    for r in refs:
        ticker_str = ", ".join(r.get("tickers", []) or [])
        chart = r.get("chart_type") or ""
        tf = r.get("timeframe") or ""
        if ticker_str and chart and tf:
            parts.append(f"{ticker_str} ({tf} {chart})")
        elif ticker_str and chart:
            parts.append(f"{ticker_str} ({chart})")
        elif ticker_str and tf:
            parts.append(f"{ticker_str} ({tf})")
        elif ticker_str:
            parts.append(ticker_str)
        elif chart and tf:
            parts.append(f"{tf} {chart}")
        elif chart:
            parts.append(chart)
        elif tf:
            parts.append(tf)
    # Dedupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return "; ".join(out)


def upsert(
    channel_index_path: Path,
    *,
    new_entry: dict,
    rollup_cap: int = 10,
) -> bool:
    """Upsert ``new_entry`` into the sentinel block of ``channel_index_path``.

    Creates the file if it doesn't exist. Preserves operator content above
    and below the sentinel markers. Returns True on success, False on any
    I/O failure (never raises).

    ``new_entry`` shape — see ``render_block`` docstring.
    """
    try:
        if channel_index_path.exists():
            content = channel_index_path.read_text(encoding="utf-8")
        else:
            content = ""
        existing = _read_existing_entries(content)
        merged = _dedupe_and_sort(existing, new_entry, cap=rollup_cap)
        new_block = render_block(merged)

        if _BLOCK_RE.search(content):
            new_content = _BLOCK_RE.sub(new_block, content)
        else:
            # First time — append block at end with a header break.
            if content and not content.endswith("\n"):
                content += "\n"
            new_content = content + ("\n" if content else "") + new_block + "\n"

        # Ensure parent dir exists.
        channel_index_path.parent.mkdir(parents=True, exist_ok=True)
        channel_index_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("vignette_updater: upsert failed for %s: %s", channel_index_path, e)
        return False


def channel_index_path_for(
    vault_root: Path, channel_rel_dir: str
) -> Path:
    """Helper — convention is ``<vault>/<channel_rel_dir>/_index.md``."""
    return vault_root / channel_rel_dir / "_index.md"
