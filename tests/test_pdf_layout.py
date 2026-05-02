"""Tests for layout-aware PDF chapter detection.

Synthetic PDFs constructed via pymupdf cover:
- chapter detection via heading-scan (large+bold "CHAPTER N" + body text)
- running-header filtering (same text on top of every page)
- single-chapter fallback when no headings present
- low-density-page warning (mostly-blank pages → possible scan)
- landscape rotation flag
- table-shaped page heuristic
- chapter pagination (start/end pages correct)

Real-PDF coverage (e.g. The Intelligent Investor) is covered separately
via UAT — the synthetic fixtures here keep the test suite hermetic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# Force a clean module load (matches the pattern in test_vault_indexer.py).
@pytest.fixture(autouse=True)
def _reset_vault_indexer_modules():
    for mod in [m for m in list(sys.modules) if m.startswith("vault_indexer")]:
        del sys.modules[mod]
    yield


def _book_pdf(path: Path, *, chapters: list[tuple[str, list[str]]], running_header: str = "RUNNING HEADER") -> None:
    """Build a synthetic publisher-style PDF.

    Each chapter starts a new page, has a 'CHAPTER N' marker at size 16
    plus a body block at size 10, and the running header is printed at
    the top of every page.
    """
    doc = pymupdf.open()
    for chap_idx, (chap_title, paragraphs) in enumerate(chapters, start=1):
        page = doc.new_page()
        # Running header at top.
        page.insert_text((50, 30), running_header, fontsize=8, fontname="helv")
        # Chapter heading.
        page.insert_text((50, 80), f"CHAPTER {chap_idx}", fontsize=16, fontname="helv")
        page.insert_text((50, 110), chap_title, fontsize=14, fontname="helv")
        # Body.
        y = 150
        for para in paragraphs:
            page.insert_text((50, y), para, fontsize=10, fontname="helv")
            y += 30
        # Page number footer.
        page.insert_text((300, 770), str(chap_idx), fontsize=8, fontname="helv")
    doc.save(str(path))
    doc.close()


def test_chapter_detection_via_heading_scan(tmp_path):
    from vault_indexer.ingest import pdf_layout

    pdf = tmp_path / "synth.pdf"
    _book_pdf(
        pdf,
        chapters=[
            ("First chapter title", ["Body paragraph one of chapter one is long enough to count.", "Another body line."]),
            ("Second chapter title", ["Body paragraph for chapter two."]),
            ("Third chapter title", ["Third chapter body content lives here."]),
        ],
    )
    analysis = pdf_layout.analyze(pdf)
    assert analysis.detection_method in ("heading_scan", "embedded_toc")
    assert len(analysis.chapters) == 3
    assert all(c.title for c in analysis.chapters)
    assert analysis.chapters[0].page_start == 0
    assert analysis.chapters[1].page_start == 1
    assert analysis.chapters[2].page_start == 2


def test_running_header_filtering(tmp_path):
    from vault_indexer.ingest import pdf_layout

    pdf = tmp_path / "synth.pdf"
    _book_pdf(
        pdf,
        chapters=[
            ("First", ["body one"]),
            ("Second", ["body two"]),
            ("Third", ["body three"]),
            ("Fourth", ["body four"]),
        ],
        running_header="REPEATING_RUNNING_HEADER_TOKEN",
    )
    analysis = pdf_layout.analyze(pdf)
    # The repeating header should be in running_text.
    found = any(
        "repeating_running_header_token" in text
        for text, _bucket in analysis.running_text
    )
    assert found, f"expected running header to be detected; got {analysis.running_text}"

    # Extracted body should NOT include the repeating header.
    body = pdf_layout.extract_chapter_text(
        pdf, analysis.chapters[0], running_text=analysis.running_text
    )
    assert "REPEATING_RUNNING_HEADER_TOKEN" not in body


def test_single_chapter_fallback_on_unstructured_pdf(tmp_path):
    from vault_indexer.ingest import pdf_layout

    pdf = tmp_path / "unstructured.pdf"
    doc = pymupdf.open()
    # 3 pages of body text only; no chapter markers.
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((50, 100), "This page has only body content. " * 5, fontsize=10)
    doc.save(str(pdf))
    doc.close()

    analysis = pdf_layout.analyze(pdf)
    assert analysis.detection_method == "single_chapter_fallback"
    assert len(analysis.chapters) == 1
    assert analysis.chapters[0].page_start == 0
    assert analysis.chapters[0].page_end == 2


def test_low_density_pages_trigger_scan_warning(tmp_path):
    from vault_indexer.ingest import pdf_layout

    pdf = tmp_path / "scan-ish.pdf"
    doc = pymupdf.open()
    # 5 nearly-empty pages (would happen if PDF is image-only / scan).
    for _ in range(5):
        page = doc.new_page()
        page.insert_text((50, 100), "x", fontsize=10)
    doc.save(str(pdf))
    doc.close()

    analysis = pdf_layout.analyze(pdf)
    assert any("scan" in w.lower() for w in analysis.warnings)


def test_landscape_page_flagged(tmp_path):
    from vault_indexer.ingest import pdf_layout

    pdf = tmp_path / "with-landscape.pdf"
    doc = pymupdf.open()
    # First page: body. Second page: rotated 90.
    p1 = doc.new_page()
    p1.insert_text((50, 100), "Body content here." * 5, fontsize=10)
    p2 = doc.new_page()
    p2.set_rotation(90)
    p2.insert_text((50, 100), "Landscape-ish content.", fontsize=10)
    doc.save(str(pdf))
    doc.close()

    analysis = pdf_layout.analyze(pdf)
    assert any("landscape" in w.lower() for w in analysis.warnings)


def test_chapter_pagination_correct(tmp_path):
    from vault_indexer.ingest import pdf_layout

    pdf = tmp_path / "synth.pdf"
    _book_pdf(
        pdf,
        chapters=[
            ("First", ["body one"]),
            ("Second", ["body two"]),
            ("Third", ["body three"]),
        ],
    )
    analysis = pdf_layout.analyze(pdf)
    assert analysis.chapters[0].page_end == 0
    assert analysis.chapters[1].page_end == 1
    assert analysis.chapters[2].page_end == 2  # last chapter ends on last page


def test_extract_chapter_text_basic(tmp_path):
    from vault_indexer.ingest import pdf_layout

    pdf = tmp_path / "synth.pdf"
    _book_pdf(
        pdf,
        chapters=[
            ("Alpha", ["alpha body content marker."]),
            ("Beta", ["beta body content marker."]),
        ],
    )
    analysis = pdf_layout.analyze(pdf)
    body_a = pdf_layout.extract_chapter_text(
        pdf, analysis.chapters[0], running_text=analysis.running_text
    )
    body_b = pdf_layout.extract_chapter_text(
        pdf, analysis.chapters[1], running_text=analysis.running_text
    )
    assert "alpha body content marker" in body_a
    assert "beta body content marker" not in body_a
    assert "beta body content marker" in body_b
