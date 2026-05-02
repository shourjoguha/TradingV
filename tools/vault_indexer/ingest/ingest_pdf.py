"""PDF ingestion — one note per detected chapter under ``Books/<slug>/``.

Layout analysis (TOC, font-size headings, running header/footer
filtering, figure / table / landscape detection) lives in
:mod:`tools.vault_indexer.ingest.pdf_layout`. This script is a thin
orchestrator: pick a slug, call ``pdf_layout.analyze``, write one
markdown file per chapter, attach the source breadcrumb, and surface
any warnings the operator should know about (low-density pages →
possible scan; landscape pages → visual content lost; etc.).

Each note's frontmatter carries a breadcrumb back to the original file
(``source_path``, ``source_sha256``, ``source_pdf_pages_total``,
``source_pages: [start, end]``) so a future vision-retrieval workflow
can re-open the PDF and read a specific page on demand. The PDF is
**not** copied into the vault.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from .common import slug, write_note
from .pdf_layout import analyze, extract_chapter_text
from ..config import CONFIG


def sha256_of_file(path: Path, *, chunk_size: int = 1 << 20) -> str:
    """Streaming SHA-256 — robust to file moves (operator can re-locate via hash)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk_size)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _parse_tags(spec: str) -> list[str]:
    """Comma-separated tag string → list of stripped tag names."""
    if not spec:
        return []
    return [t.strip() for t in spec.split(",") if t.strip()]


def _chapter_filename(idx: int, title: str) -> str:
    """Stable, sort-friendly filename. Numeric prefix preserves chapter order
    even when titles slugify to the same string."""
    body = slug(title) or f"chapter-{idx:02d}"
    return f"{idx:02d}-{body}.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="Path to the PDF file.")
    ap.add_argument("--title", default=None, help="Override book title.")
    ap.add_argument("--author", default=None)
    ap.add_argument("--published", default=None, help="YYYY-MM-DD")
    ap.add_argument("--book-slug", default=None, help="Folder slug under Books/")
    ap.add_argument(
        "--single-chapter",
        action="store_true",
        help="Skip the layout-aware chapter splitter; one note for the whole PDF.",
    )
    ap.add_argument(
        "--tags",
        default="",
        help=(
            "Comma-separated tags to apply to every note (book index + chapters). "
            "Tags should be members of the controlled vocabulary in _taxonomy.md."
        ),
    )
    args = ap.parse_args()

    pdf_path = Path(args.path).expanduser().resolve()
    if not pdf_path.exists():
        print(f"not found: {pdf_path}", file=sys.stderr)
        return 1

    title = args.title or pdf_path.stem.replace("-", " ").title()
    book_slug = args.book_slug or slug(title)
    rel_dir = f"Books/{book_slug}"
    tags = _parse_tags(args.tags)
    sha = sha256_of_file(pdf_path)
    breadcrumb = {
        "source_path": str(pdf_path),
        "source_sha256": sha,
    }

    if args.single_chapter:
        # Bypass the analyzer; treat the whole PDF as one chapter via a
        # cheap text dump. Useful when layout detection misbehaves on a
        # specific PDF and the operator just wants the text in.
        import pymupdf

        with pymupdf.open(str(pdf_path)) as doc:
            full = "\n\n".join(p.get_text("text") for p in doc)
            page_count = doc.page_count
        breadcrumb["source_pdf_pages_total"] = page_count
        write_note(
            vault_root=CONFIG.vault_path,
            rel_dir=rel_dir,
            filename="index.md",
            body=f"# {title}\n\nAuthor: {args.author or '—'}\n\n*Single-chapter ingestion (layout-aware splitting bypassed).*",
            metadata={
                "kind": "book",
                "title": title,
                "author": args.author,
                "published_at": args.published,
                "tags": list(tags),
                **breadcrumb,
                "source_pages": [0, page_count - 1],
            },
        )
        write_note(
            vault_root=CONFIG.vault_path,
            rel_dir=rel_dir,
            filename="01-full-text.md",
            body=f"# {title}\n\n{full}",
            metadata={
                "kind": "book_chapter",
                "title": f"{title} — Full text",
                "author": args.author,
                "published_at": args.published,
                "parent": f"{rel_dir}/index.md",
                "tags": list(tags),
                **breadcrumb,
                "source_pages": [0, page_count - 1],
            },
        )
        print(f"ingested 1 single-chapter note under {rel_dir}/")
        return 0

    print(f"analyzing layout of {pdf_path.name} ({pdf_path.stat().st_size / 1e6:.1f} MB)…")
    analysis = analyze(pdf_path)
    breadcrumb["source_pdf_pages_total"] = analysis.page_count

    print(
        f"  detection method: {analysis.detection_method}  |  "
        f"chapters: {len(analysis.chapters)}  |  body size: {analysis.body_size}  |  "
        f"body font: {analysis.body_font}"
    )
    for w in analysis.warnings:
        print(f"  [warn] {w}")

    if not analysis.chapters:
        print("no chapters detected — aborting", file=sys.stderr)
        return 2

    # Index note linking the chapters.
    index_lines = [
        f"# {title}",
        "",
        f"Author: {args.author or '—'}",
        f"Detection: {analysis.detection_method}",
        f"Pages: {analysis.page_count}",
        "",
        "## Chapters",
        "",
    ]
    for i, ch in enumerate(analysis.chapters, start=1):
        flags = []
        if ch.has_figures:
            flags.append("figures")
        if ch.has_tables:
            flags.append("tables")
        if ch.has_landscape_pages:
            flags.append("landscape")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        chap_filename = _chapter_filename(i, ch.title)
        index_lines.append(
            f"- [[{book_slug}/{chap_filename[:-3]}|{ch.title}]]"
            f" (pp. {ch.page_start + 1}-{ch.page_end + 1}){flag_str}"
        )

    write_note(
        vault_root=CONFIG.vault_path,
        rel_dir=rel_dir,
        filename="index.md",
        body="\n".join(index_lines),
        metadata={
            "kind": "book",
            "title": title,
            "author": args.author,
            "published_at": args.published,
            "tags": list(tags),
            **breadcrumb,
        },
    )

    written = 0
    for i, ch in enumerate(analysis.chapters, start=1):
        body_text = extract_chapter_text(
            pdf_path, ch, running_text=analysis.running_text
        )
        if not body_text.strip():
            print(f"  [skip] chapter {i:02d} {ch.title!r} produced empty body text")
            continue
        flags: list[str] = []
        if ch.has_figures:
            flags.append("figures")
        if ch.has_tables:
            flags.append("tables")
        if ch.has_landscape_pages:
            flags.append("landscape")
        # Tags = global tags + chapter-specific flag tags. Flag tags help
        # the operator filter Obsidian for chapters with charts/tables
        # without re-reading the index.
        tag_set = list(tags)
        for f in flags:
            tag = f"chapter_has_{f}"
            if tag not in tag_set:
                tag_set.append(tag)
        write_note(
            vault_root=CONFIG.vault_path,
            rel_dir=rel_dir,
            filename=_chapter_filename(i, ch.title),
            body=f"# {ch.title}\n\n{body_text}",
            metadata={
                "kind": "book_chapter",
                "title": f"{title} — {ch.title}",
                "author": args.author,
                "published_at": args.published,
                "parent": f"{rel_dir}/index.md",
                "tags": tag_set,
                "source_pages": [ch.page_start + 1, ch.page_end + 1],
                **breadcrumb,
            },
        )
        written += 1

    print(f"ingested {written}/{len(analysis.chapters)} chapter(s) under {rel_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
