"""Verify ingestion writes the source-breadcrumb frontmatter so future
vision-retrieval workflows can find the original file.

PDF + EPUB ingestion writes ``source_path``, ``source_sha256``, and
(PDFs only) ``source_pdf_pages_total``. Video + newsletter already
preserve ``source_url``; covered indirectly via the existing test
that they round-trip through write_note.
"""
from __future__ import annotations

import sys
from pathlib import Path

import frontmatter
import pytest


@pytest.fixture
def vault_root(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("INDEXER_DB_PATH", str(tmp_path / ".indexer" / "cache.db"))
    monkeypatch.setenv("AUTO_TAG_ENABLED", "0")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    for mod in [m for m in list(sys.modules) if m == "vault_indexer" or m.startswith("vault_indexer.")]:
        del sys.modules[mod]
    return tmp_path


def _make_minimal_pdf(path: Path) -> None:
    """Generate a single-page PDF with one line of text via pymupdf."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world. CHAPTER ONE\n\nSome content under chapter one.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "More content on page two.")
    doc.save(str(path))
    doc.close()


def test_pdf_ingest_writes_source_breadcrumb(vault_root, monkeypatch):
    pdf = vault_root.parent / "test.pdf"
    _make_minimal_pdf(pdf)

    from vault_indexer.ingest import ingest_pdf

    monkeypatch.setattr(
        sys, "argv",
        ["ingest_pdf", "--path", str(pdf), "--title", "Test Book", "--single-chapter"],
    )
    rc = ingest_pdf.main()
    assert rc == 0

    # New layout-aware ingest prefixes chapter filenames with a sort-stable
    # numeric prefix; single-chapter mode emits "01-full-text.md".
    chapter = vault_root / "Books" / "test-book" / "01-full-text.md"
    assert chapter.exists(), f"expected chapter at {chapter}, got {list(vault_root.rglob('*.md'))}"
    post = frontmatter.loads(chapter.read_text(encoding="utf-8"))

    assert post.metadata["source_path"] == str(pdf)
    sha = post.metadata["source_sha256"]
    assert isinstance(sha, str) and len(sha) == 64
    assert post.metadata["source_pdf_pages_total"] == 2

    # Index also gets the breadcrumb.
    index = vault_root / "Books" / "test-book" / "index.md"
    idx = frontmatter.loads(index.read_text(encoding="utf-8"))
    assert idx.metadata["source_sha256"] == sha


def test_pdf_sha_changes_with_content(vault_root):
    """The hash should differ for different files — sanity check on the
    re-locate-by-hash story."""
    from vault_indexer.ingest.ingest_pdf import sha256_of_file

    a = vault_root.parent / "a.pdf"
    b = vault_root.parent / "b.pdf"
    _make_minimal_pdf(a)
    # Distinct content
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "different content")
    doc.save(str(b))
    doc.close()

    assert sha256_of_file(a) != sha256_of_file(b)
