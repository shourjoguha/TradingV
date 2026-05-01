"""Newsletter ingestion — URL or text-file input → markdown into Newsletters/."""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from .common import iso_week, slug, write_note
from ..config import CONFIG


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", required=True, help="Slug for the author folder.")
    ap.add_argument("--horizon", type=int, default=3, help="horizon_months for decay.")
    ap.add_argument("--published", default=None, help="YYYY-MM-DD; defaults to today.")
    ap.add_argument("--url", default=None)
    ap.add_argument("--text-file", default=None, help="Path to a text/markdown file with the newsletter body.")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    if not (args.url or args.text_file):
        print("provide --url or --text-file", file=sys.stderr)
        return 1

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
            "tags": [],
        },
    )
    print(f"ingested → {rel_dir}/{filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
