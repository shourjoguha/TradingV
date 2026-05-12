"""Newsletter ingestion — URL / text-file / RSS-feed input → markdown into Newsletters/.

Three modes:
  • ``--url``       single URL → one markdown file
  • ``--text-file`` local file → one markdown file
  • ``--feed``      RSS/Atom feed → one markdown file per entry, idempotent
                    on the entry's GUID/link
"""
from __future__ import annotations

import argparse
import datetime
import logging
import re
import sys
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

from .common import iso_week, slug, write_note
from ..config import CONFIG

logger = logging.getLogger(__name__)


def fetch_url(url: str) -> tuple[str, str]:
    """Return (title, body_text) for the URL, using readability-lxml."""
    import urllib.request

    from readability import Document

    req = urllib.request.Request(url, headers={"User-Agent": "vault-indexer/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    doc = Document(html)
    title = doc.short_title() or "Untitled"
    # Convert to plain text.
    from lxml.html import fromstring
    tree = fromstring(doc.summary())
    body = "\n\n".join(p.text_content().strip() for p in tree.iter() if p.tag in {"p", "blockquote", "li"} and p.text_content().strip())
    return title, body


# ---------------------------------------------------------------------------
# RSS / Atom feed support
# ---------------------------------------------------------------------------

# Newsletters are typically RSS 2.0; major government feeds (Fed, Treasury, SEC)
# vary. We parse both shapes by walking common child names without binding to
# a specific namespace map.

_RSS_DATE_FORMATS = (
    "%a, %d %b %Y %H:%M:%S %z",     # RFC 822 (RSS 2.0)
    "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S%z",          # ISO 8601 (Atom)
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
)


def _parse_pub_date(raw: str) -> Optional[datetime.date]:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _RSS_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    # Last-ditch: take first 10 chars as ISO date.
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _local_name(elem: ET.Element) -> str:
    """Strip namespace prefix from an element tag."""
    tag = elem.tag
    return tag.split("}", 1)[1] if "}" in tag else tag


def _child_text(parent: ET.Element, *names: str) -> Optional[str]:
    """First non-empty text of the first matching child by local-name."""
    name_set = {n.lower() for n in names}
    for child in parent:
        if _local_name(child).lower() in name_set:
            text = (child.text or "").strip()
            if text:
                return text
            # Atom <link> uses an attribute, not text content.
            href = child.attrib.get("href", "").strip()
            if href:
                return href
    return None


from dataclasses import dataclass


@dataclass(frozen=True)
class _FeedEntry:
    title: str
    link: str
    pub_date: Optional[datetime.date]
    summary: str
    guid: str  # falls back to `link` when no GUID present


def parse_feed(xml_bytes: bytes) -> list[_FeedEntry]:
    """Parse RSS 2.0 OR Atom feeds. Returns entries with normalised fields.

    The parser is namespace-agnostic so government feeds (Fed, Treasury,
    SEC) and standard RSS feeds (Reuters, etc.) both work without a
    namespace map.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("feed parse failed: %s", e)
        return []

    out: list[_FeedEntry] = []

    # RSS 2.0 = <rss><channel><item>...; Atom = <feed><entry>...
    items: list[ET.Element] = []
    for child in root.iter():
        local = _local_name(child).lower()
        if local in {"item", "entry"}:
            items.append(child)

    for it in items:
        title = _child_text(it, "title") or "Untitled"
        link = _child_text(it, "link") or ""
        pub = _child_text(it, "pubdate", "published", "updated", "date")
        summary = _child_text(it, "description", "summary", "content") or ""
        guid = _child_text(it, "guid", "id") or link
        if not guid:
            continue
        out.append(
            _FeedEntry(
                title=title.strip(),
                link=link.strip(),
                pub_date=_parse_pub_date(pub or ""),
                summary=summary.strip(),
                guid=guid.strip(),
            )
        )
    return out


def _existing_guids(target_dir: Path) -> set[str]:
    """Scan the target newsletter folder for already-ingested GUIDs.

    The ingester writes the GUID into frontmatter as ``source_guid`` so
    re-runs are idempotent. Returns the set of GUIDs already present.
    """
    if not target_dir.is_dir():
        return set()
    out: set[str] = set()
    for md in target_dir.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(r"^source_guid:\s*['\"]?([^'\"\n]+)['\"]?\s*$", text, re.MULTILINE)
        if m:
            out.add(m.group(1).strip())
    return out


def ingest_feed(
    *,
    feed_url: str,
    author: str,
    horizon_months: int = 3,
    tags: Optional[list[str]] = None,
    max_entries: int = 5,
    vault_root: Optional[Path] = None,
) -> dict:
    """Fetch + ingest a feed. Idempotent on entry GUID. Returns summary dict.

    The feed URL is fetched once; entries already in the target folder are
    skipped. Entries with extracted bodies that fail to parse are skipped
    (logged at warning level).
    """
    import urllib.request

    root = vault_root or CONFIG.vault_path
    rel_dir = f"Newsletters/{slug(author)}"
    target_dir = root / rel_dir
    seen = _existing_guids(target_dir)

    req = urllib.request.Request(
        feed_url, headers={"User-Agent": "vault-indexer/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_bytes = resp.read()
    except Exception as e:                                 # noqa: BLE001
        logger.warning("feed fetch failed for %s: %s", feed_url, e)
        return {"feed": feed_url, "error": str(e)}

    entries = parse_feed(xml_bytes)
    new_entries = [e for e in entries if e.guid not in seen][:max_entries]

    written = 0
    written_paths: list[str] = []
    for entry in new_entries:
        # Prefer fetching the full article when a link is present; fall
        # back to the feed-supplied summary otherwise.
        title = entry.title
        body: str
        if entry.link:
            try:
                fetched_title, fetched_body = fetch_url(entry.link)
                if fetched_body:
                    if fetched_title and len(fetched_title) > 5:
                        title = fetched_title
                    body = fetched_body
                else:
                    body = entry.summary
            except Exception as e:                         # noqa: BLE001
                logger.warning("body fetch failed for %s: %s", entry.link, e)
                body = entry.summary
        else:
            body = entry.summary

        if not body:
            continue

        published = (entry.pub_date or datetime.date.today()).isoformat()
        week = iso_week(datetime.date.fromisoformat(published))
        filename = f"{week}-{slug(title)[:60]}.md"
        path = write_note(
            vault_root=root,
            rel_dir=rel_dir,
            filename=filename,
            body=f"# {title}\n\n{body}",
            metadata={
                "kind": "newsletter",
                "title": title,
                "author": author,
                "source_url": entry.link or feed_url,
                "source_guid": entry.guid,
                "published_at": published,
                "horizon_months": horizon_months,
                "tags": tags or [],
            },
        )
        written += 1
        written_paths.append(str(path.relative_to(root)))
        seen.add(entry.guid)

    return {
        "feed": feed_url,
        "author": author,
        "fetched": len(entries),
        "written": written,
        "skipped": len(entries) - written,
        "written_paths": written_paths,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", required=True, help="Slug for the author folder.")
    ap.add_argument("--horizon", type=int, default=3, help="horizon_months for decay.")
    ap.add_argument("--published", default=None, help="YYYY-MM-DD; defaults to today.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", default=None, help="Single article URL.")
    src.add_argument(
        "--text-file",
        default=None,
        help="Path to a text/markdown file with the newsletter body.",
    )
    src.add_argument(
        "--feed",
        default=None,
        help="RSS/Atom feed URL. Idempotent on GUID; fetches up to --max-entries.",
    )
    ap.add_argument("--title", default=None)
    ap.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=None,
        help="Tag (repeatable). Applied to every entry.",
    )
    ap.add_argument(
        "--max-entries",
        type=int,
        default=5,
        help="Cap entries ingested per feed run (default 5).",
    )
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.feed:
        result = ingest_feed(
            feed_url=args.feed,
            author=args.author,
            horizon_months=args.horizon,
            tags=args.tags,
            max_entries=args.max_entries,
        )
        print(result)
        return 0 if result.get("written", 0) >= 0 and "error" not in result else 1

    if args.url:
        title, body = fetch_url(args.url)
    else:
        body = Path(args.text_file).expanduser().read_text(encoding="utf-8")
        title = args.title or Path(args.text_file).stem
    if args.title:
        title = args.title

    published = args.published or datetime.date.today().isoformat()
    week = iso_week(datetime.date.fromisoformat(published))
    rel_dir = f"Newsletters/{slug(args.author)}"
    filename = f"{week}-{slug(title)}.md"

    write_note(
        vault_root=CONFIG.vault_path,
        rel_dir=rel_dir,
        filename=filename,
        body=f"# {title}\n\n{body}",
        metadata={
            "kind": "newsletter",
            "title": title,
            "author": args.author,
            "source_url": args.url,
            "published_at": published,
            "horizon_months": args.horizon,
            "tags": args.tags or [],
        },
    )
    print(f"ingested → {rel_dir}/{filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
