"""PDF ingestion — split by `# heading` into chapter notes under `Books/`."""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import pymupdf

from .common import iso_week, slug, write_note          # noqa: F401 (kept for symmetry)
from ..config import CONFIG


def extract_text(pdf_path: Path) -> str:
    with pymupdf.open(pdf_path) as doc:
        parts = []
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n\n".join(parts)


def split_by_chapters(raw: str) -> list[tuple[str, str]]:
    """Best-effort chapter split. Looks for ALL-CAPS lines or 'Chapter N'
    markers and treats them as chapter starts. Falls back to a single chunk."""
    lines = raw.splitlines()
    chapters: list[tuple[str, list[str]]] = [("Front matter", [])]
    for line in lines:
        stripped = line.strip()
        if (
            stripped.startswith("Chapter ")
            or (stripped.isupper() and 5 <= len(stripped) <= 80)
        ):
            chapters.append((stripped.title(), []))
        else:
            chapters[-1][1].append(line)
    out = []
    for title, body in chapters:
        text = "\n".join(body).strip()
        if text:
            out.append((title, text))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="Path to the PDF file.")
    ap.add_argument("--title", default=None, help="Override book title.")
    ap.add_argument("--author", default=None)
    ap.add_argument("--published", default=None, help="YYYY-MM-DD")
    ap.add_argument("--book-slug", default=None, help="Folder slug under Books/")
    ap.add_argument("--single-chapter", action="store_true", help="Skip chapter split; one note for the whole PDF.")
    args = ap.parse_args()

    pdf_path = Path(args.path).expanduser().resolve()
    if not pdf_path.exists():
        print(f"not found: {pdf_path}", file=sys.stderr)
        return 1

    title = args.title or pdf_path.stem.replace("-", " ").title()
    book_slug = args.book_slug or slug(title)
    rel_dir = f"Books/{book_slug}"

    raw = extract_text(pdf_path)
    if args.single_chapter:
        chapters = [("Full text", raw)]
    else:
        chapters = split_by_chapters(raw)
    if not chapters:
        print("no extractable text", file=sys.stderr)
        return 2

    vault_root = CONFIG.vault_path

    # Index note linking the chapters.
    index_body = f"# {title}\n\nAuthor: {args.author or '—'}\n\n## Chapters\n"
    for i, (chap_title, _) in enumerate(chapters, start=1):
        cslug = slug(chap_title) or f"ch-{i:02d}"
        index_body += f"- [[{book_slug}-{cslug}|{chap_title}]]\n"
    write_note(
        vault_root=vault_root,
        rel_dir=rel_dir,
        filename="index.md",
        body=index_body,
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
