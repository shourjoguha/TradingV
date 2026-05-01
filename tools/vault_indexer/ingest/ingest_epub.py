"""EPUB ingestion via ebooklib — chapter-aware."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ebooklib import epub
from lxml.html import fromstring as parse_html, tostring

from .common import slug, write_note
from ..config import CONFIG


def extract_chapters(epub_path: Path) -> list[tuple[str, str]]:
    book = epub.read_epub(str(epub_path))
    out = []
    for item in book.get_items():
        if item.get_type() != 9:                      # ITEM_DOCUMENT
            continue
        try:
            tree = parse_html(item.get_content())
        except Exception:                              # noqa: BLE001
            continue
        # Title from first h1 / h2 / heading-ish element.
        h = tree.find(".//h1") or tree.find(".//h2")
        title = (h.text_content().strip() if h is not None else item.get_name()) or "Untitled"
        text = "\n\n".join(p.text_content().strip() for p in tree.iter() if p.tag in {"p", "blockquote"} and p.text_content().strip())
        if text:
            out.append((title, text))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--author", default=None)
    ap.add_argument("--published", default=None)
    ap.add_argument("--book-slug", default=None)
    args = ap.parse_args()

    p = Path(args.path).expanduser().resolve()
    if not p.exists():
        print(f"not found: {p}", file=sys.stderr)
        return 1

    title = args.title or p.stem.replace("-", " ").title()
    book_slug = args.book_slug or slug(title)
    rel_dir = f"Books/{book_slug}"

    chapters = extract_chapters(p)
    if not chapters:
        print("no extractable chapters", file=sys.stderr)
        return 2

    vault_root = CONFIG.vault_path
    write_note(
        vault_root=vault_root,
        rel_dir=rel_dir,
        filename="index.md",
        body=f"# {title}\n\nAuthor: {args.author or '—'}\n",
        metadata={
            "kind": "book",
            "title": title,
            "author": args.author,
            "published_at": args.published,
            "tags": [],
        },
    )
    for i, (chap_title, body) in enumerate(chapters, start=1):
        cslug = slug(chap_title) or f"ch-{i:02d}"
        write_note(
            vault_root=vault_root,
            rel_dir=rel_dir,
            filename=f"{cslug}.md",
            body=f"# {chap_title}\n\n{body}",
            metadata={
                "kind": "book_chapter",
                "title": f"{title} — {chap_title}",
                "author": args.author,
                "published_at": args.published,
                "parent": f"{rel_dir}/index.md",
                "tags": [],
            },
        )
    print(f"ingested {len(chapters)} chapter(s) under {rel_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
