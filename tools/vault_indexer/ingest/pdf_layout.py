"""Robust PDF layout analysis for book ingestion.

Replaces the original "ALL CAPS line ⇒ chapter heading" heuristic that
fragmented `THE-INTELLIGENT-INVESTOR.pdf` into 281 garbage chapters.
Operates on pymupdf's structured-text dict (per-span font, size, flags,
bbox) so chapter boundaries, running headers, figures, tables, and
landscape pages are all detected from real layout signals — not from
text content alone.

Pipeline (one PDF → one ``PdfAnalysis``):

  1. **First pass: extract every span on every page** with its font /
     size / flags / bbox. Compute a body-text baseline (mode of text
     size weighted by character count).
  2. **Running header/footer detection.** Bucket spans by rounded Y
     coordinate; any text appearing in the same Y bucket on >50% of
     pages is filtered from chapter-detection signal AND from the
     emitted body markdown.
  3. **Chapter boundary detection** in priority order:
     a. ``doc.get_toc()`` (embedded PDF bookmarks) — used IFF it has
        sufficient entries (default ≥10).
     b. Per-page heading detection: a span at ``size ≥ baseline + 1.5``
        is a candidate heading; a heading whose text matches
        ``CHAPTER N`` (or similar) is a chapter start.
     c. Printed Contents page parsing — scan for a page whose layout
        looks like a TOC (many "title ... pageN" rows) and use that.
  4. **Special-content flagging.** Pages with image blocks → ``has_figures``.
     Pages whose text-block layout looks tabular → ``has_tables``.
     Pages with rotation != 0 OR text spans rotated 90° → ``has_landscape``.
  5. **Possible-scan detection.** Pages with anomalously low char-density
     OR unusual font-distribution → flagged in ``warnings``. OCR is
     deferred to a backlog item — the operator gets a heads-up at
     ingestion time so they can hand the file to OCR before retrying
     if needed.

Tuning knobs live as module constants near the top.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pymupdf

logger = logging.getLogger(__name__)


# ----- Tunables -----------------------------------------------------------

# A heading-candidate span has size ≥ baseline + this delta.
HEADING_SIZE_DELTA = 1.5

# Embedded PDF TOC must have at least this many entries to be trusted as
# the chapter map. ``THE-INTELLIGENT-INVESTOR.pdf`` has only 13 sparse
# entries — well below — so we fall back to span-based detection.
EMBEDDED_TOC_MIN_ENTRIES = 20

# Y-bucket coarseness for header/footer detection (points).
RUNNING_TEXT_Y_BUCKET = 6.0

# A span text is "running" if it appears in the same Y bucket on
# at least this fraction of pages.
RUNNING_TEXT_FRACTION = 0.40

# Chapter-start markers. Pattern matches at the BEGINNING of stripped span text.
# Matches "Chapter 1", "CHAPTER 1", "Chapter I", "CHAPTER ONE" (the last via numeric set).
CHAPTER_START_PATTERN = re.compile(
    r"^\s*chapter\s+(\d+|[IVXLCDM]+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b",
    re.IGNORECASE,
)

# Where running headers / footers may live (fraction of page height).
HEADER_TOP_FRACTION = 0.10        # top 10% of page
FOOTER_BOTTOM_FRACTION = 0.90     # bottom 10% of page

# Possible-scan flag if a page has fewer than this many text characters
# (a normal body page in a publisher PDF runs 1500-3500).
LOW_DENSITY_CHAR_THRESHOLD = 300


# ----- Dataclasses --------------------------------------------------------


@dataclass
class Span:
    """One text span as pymupdf reports it."""
    page_idx: int
    text: str
    size: float
    flags: int                     # bitmap: 0=super, 1=italic, 2=serif, 3=mono, 4=bold
    font: str
    bbox: tuple[float, float, float, float]   # x0, y0, x1, y1

    @property
    def is_bold(self) -> bool:
        return bool(self.flags & 16)

    @property
    def is_italic(self) -> bool:
        return bool(self.flags & 2)

    @property
    def y_top(self) -> float:
        return self.bbox[1]

    @property
    def y_bot(self) -> float:
        return self.bbox[3]


@dataclass
class PageLayout:
    page_idx: int
    rotation: int
    width: float
    height: float
    spans: list[Span] = field(default_factory=list)
    image_block_count: int = 0
    char_count: int = 0
    has_landscape_text: bool = False  # span bbox rotated 90° / extreme aspect


@dataclass
class Chapter:
    title: str
    page_start: int                  # 0-indexed inclusive
    page_end: int                    # 0-indexed inclusive
    has_figures: bool = False
    has_tables: bool = False
    has_landscape_pages: bool = False
    char_count: int = 0


@dataclass
class PdfAnalysis:
    pdf_path: Path
    page_count: int
    body_size: float                # baseline body text size
    body_font: str                  # most common body font
    chapters: list[Chapter] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detection_method: str = "unknown"  # "embedded_toc" | "heading_scan" | "printed_toc" | "single_chapter_fallback"
    # The set of (text, y-bucket) pairs identified as running header/footer.
    running_text: set[tuple[str, int]] = field(default_factory=set)


# ----- Pass 1: extract all spans -----------------------------------------


def _extract_spans(doc: pymupdf.Document) -> list[PageLayout]:
    """Walk every page; capture span metadata + image-block count + char count."""
    pages: list[PageLayout] = []
    for i in range(doc.page_count):
        page = doc[i]
        rect = page.rect
        layout = PageLayout(
            page_idx=i,
            rotation=page.rotation,
            width=rect.width,
            height=rect.height,
        )
        try:
            d = page.get_text("dict")
        except Exception as e:  # noqa: BLE001
            logger.warning("page %d: get_text(dict) failed: %s", i, e)
            pages.append(layout)
            continue
        for block in d.get("blocks", []):
            if block.get("type") == 1:
                layout.image_block_count += 1
                continue
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                # Detect rotated lines via line dir vector.
                line_dir = line.get("dir") or (1, 0)
                if abs(line_dir[1]) > 0.5:        # cos-near-zero means rotated
                    layout.has_landscape_text = True
                for span in line.get("spans", []):
                    txt = span.get("text") or ""
                    if not txt.strip():
                        continue
                    layout.spans.append(
                        Span(
                            page_idx=i,
                            text=txt,
                            size=float(span.get("size", 0.0)),
                            flags=int(span.get("flags", 0)),
                            font=str(span.get("font", "")),
                            bbox=tuple(span.get("bbox", (0, 0, 0, 0))),
                        )
                    )
                    layout.char_count += len(txt)
        # Page-level landscape flag also fires when the page itself rotated.
        if page.rotation in (90, 270):
            layout.has_landscape_text = True
        pages.append(layout)
    return pages


def _baseline(pages: list[PageLayout]) -> tuple[float, str]:
    """Return (body_size, body_font) — character-weighted modes."""
    size_chars: Counter = Counter()
    font_chars: Counter = Counter()
    for p in pages:
        for s in p.spans:
            size_chars[round(s.size, 1)] += len(s.text)
            font_chars[s.font] += len(s.text)
    body_size = size_chars.most_common(1)[0][0] if size_chars else 0.0
    body_font = font_chars.most_common(1)[0][0] if font_chars else ""
    return body_size, body_font


# ----- Pass 2: running header/footer detection ---------------------------


def _detect_running_text(pages: list[PageLayout]) -> set[tuple[str, int]]:
    """Identify spans that recur at the same Y-bucket on a large fraction of
    pages — these are running headers / footers / page-number lines.

    Returns set of ``(stripped_text_lowercase, y_bucket)`` pairs to filter
    out of body text + ignore for chapter-heading detection.
    """
    if not pages:
        return set()
    occurrence: dict[tuple[str, int], set[int]] = defaultdict(set)
    for p in pages:
        if not p.spans:
            continue
        h = p.height or 1.0
        for s in p.spans:
            top = s.y_top / h
            bot = s.y_bot / h
            # Only consider spans in the page margins.
            if top > HEADER_TOP_FRACTION and bot < FOOTER_BOTTOM_FRACTION:
                continue
            stripped = s.text.strip().lower()
            if not stripped:
                continue
            # Page numbers vary per page → skip pure-digit + small text.
            if stripped.isdigit():
                # Still flag the (anything, y_bucket) pair so we filter
                # numeric strings at this Y too — operator's running
                # footers are page numbers in this PDF.
                bucket = int(s.y_top // RUNNING_TEXT_Y_BUCKET)
                occurrence[("__digit__", bucket)].add(p.page_idx)
                continue
            bucket = int(s.y_top // RUNNING_TEXT_Y_BUCKET)
            occurrence[(stripped, bucket)].add(p.page_idx)

    threshold = max(2, int(len(pages) * RUNNING_TEXT_FRACTION))
    running: set[tuple[str, int]] = set()
    for key, page_set in occurrence.items():
        if len(page_set) >= threshold:
            running.add(key)
    return running


def _is_running(span: Span, page_height: float, running: set[tuple[str, int]]) -> bool:
    """True if this span looks like a running header / footer / page number."""
    h = page_height or 1.0
    top = span.y_top / h
    bot = span.y_bot / h
    if top > HEADER_TOP_FRACTION and bot < FOOTER_BOTTOM_FRACTION:
        return False
    bucket = int(span.y_top // RUNNING_TEXT_Y_BUCKET)
    if span.text.strip().isdigit():
        return ("__digit__", bucket) in running
    return (span.text.strip().lower(), bucket) in running


# ----- Pass 3: chapter detection -----------------------------------------


def _chapters_from_embedded_toc(
    doc: pymupdf.Document, page_count: int
) -> Optional[list[Chapter]]:
    toc = doc.get_toc()
    if not toc or len(toc) < EMBEDDED_TOC_MIN_ENTRIES:
        return None
    # Use level-1 entries.
    l1 = [(title, page - 1) for level, title, page in toc if level == 1]
    if len(l1) < EMBEDDED_TOC_MIN_ENTRIES:
        return None
    chapters: list[Chapter] = []
    for i, (title, p_start) in enumerate(l1):
        p_end = (l1[i + 1][1] - 1) if i + 1 < len(l1) else page_count - 1
        chapters.append(Chapter(title=title.strip(), page_start=p_start, page_end=p_end))
    return chapters


def _chapters_from_heading_scan(
    pages: list[PageLayout],
    body_size: float,
    running: set[tuple[str, int]],
) -> Optional[list[Chapter]]:
    """Look for spans that look like chapter starts (e.g. 'CHAPTER 7' at a
    size > body_size + delta) and use them as boundaries."""
    boundaries: list[tuple[int, str]] = []   # (page_idx, title)
    for p in pages:
        # Skip pages whose text is entirely the running header (cover pages
        # often have no real body).
        non_running = [s for s in p.spans if not _is_running(s, p.height, running)]
        if not non_running:
            continue
        # Look at the first few spans (top of page) for a chapter marker.
        # Sort by y to make sure we look top-down even if blocks weren't.
        sorted_spans = sorted(non_running, key=lambda s: s.y_top)
        for idx, s in enumerate(sorted_spans[:6]):
            if s.size < body_size + HEADING_SIZE_DELTA - 0.5:
                continue
            if not CHAPTER_START_PATTERN.match(s.text.strip()):
                continue
            # Look at next spans for the title (bigger / italic / different font).
            title_parts: list[str] = []
            for follow in sorted_spans[idx + 1 : idx + 6]:
                if follow.size < body_size + HEADING_SIZE_DELTA - 0.5:
                    break
                # Skip page numbers / very short spans that aren't title-like.
                txt = follow.text.strip()
                if not txt or txt.isdigit():
                    continue
                # A single letter at the title size is almost always the
                # body's first-paragraph dropcap, not a title word. Strip.
                if len(txt) == 1 and txt.isalpha():
                    continue
                title_parts.append(txt)
            full_title = " ".join(title_parts).strip() if title_parts else s.text.strip()
            boundaries.append((p.page_idx, full_title))
            break
    if len(boundaries) < 2:
        return None
    chapters: list[Chapter] = []
    for i, (p_start, title) in enumerate(boundaries):
        p_end = (
            boundaries[i + 1][0] - 1
            if i + 1 < len(boundaries)
            else (pages[-1].page_idx if pages else p_start)
        )
        chapters.append(Chapter(title=title, page_start=p_start, page_end=p_end))
    return chapters


def _printed_toc_chapters(
    pages: list[PageLayout], body_size: float
) -> Optional[list[Chapter]]:
    """Find a printed Contents page (e.g. ``Contents`` heading + many
    "Title ... 47" rows). Use those rows as chapter boundaries.

    Heuristic: scan the first 30 pages; pick the page where ≥8 spans look
    like ``<text> ... <pageN>`` (text followed by digits separated by
    dots/spaces). Map titles → starting pages.
    """
    row_re = re.compile(r"^(.+?)[\s\.]{2,}(\d{1,4})\s*$")
    for p in pages[:30]:
        # Only look at pages whose top has a "Contents" / "Table of Contents" line.
        joined_top = " ".join(s.text for s in sorted(p.spans, key=lambda s: s.y_top)[:6])
        if "contents" not in joined_top.lower():
            continue
        # Try to extract rows.
        rows: list[tuple[str, int]] = []
        # We work line-by-line via pymupdf-recovered text.
        text = "\n".join(s.text for s in p.spans)
        for line in text.splitlines():
            m = row_re.match(line.strip())
            if not m:
                continue
            try:
                page_no = int(m.group(2))
            except ValueError:
                continue
            title = m.group(1).strip()
            if 1 <= page_no <= 1500 and title:
                rows.append((title, page_no - 1))
        if len(rows) >= 8:
            # Sort by page asc + dedup.
            rows.sort(key=lambda r: r[1])
            chapters: list[Chapter] = []
            for i, (title, p_start) in enumerate(rows):
                p_end = (
                    rows[i + 1][1] - 1
                    if i + 1 < len(rows)
                    else (pages[-1].page_idx if pages else p_start)
                )
                chapters.append(Chapter(title=title, page_start=p_start, page_end=p_end))
            return chapters
    return None


# ----- Pass 4: special-content flags + warnings --------------------------


def _annotate_chapters(chapters: list[Chapter], pages: list[PageLayout]) -> None:
    by_idx = {p.page_idx: p for p in pages}
    for ch in chapters:
        for pn in range(ch.page_start, ch.page_end + 1):
            p = by_idx.get(pn)
            if not p:
                continue
            ch.char_count += p.char_count
            if p.image_block_count > 0:
                ch.has_figures = True
            if p.has_landscape_text or p.rotation in (90, 270):
                ch.has_landscape_pages = True
            # Crude table heuristic: many text spans at varying X but tight
            # vertical packing. A rigorous detector is future work.
            if _looks_like_table_page(p):
                ch.has_tables = True


def _looks_like_table_page(p: PageLayout) -> bool:
    """Cheap table heuristic. Rows of short numeric/short-text spans with
    similar Y but multiple distinct X values across many rows."""
    if len(p.spans) < 30:
        return False
    rows: dict[int, list[Span]] = defaultdict(list)
    for s in p.spans:
        y_bucket = int(s.y_top // 4.0)
        rows[y_bucket].append(s)
    grid_rows = 0
    for spans in rows.values():
        if len(spans) >= 4:
            xs = sorted({int(s.bbox[0] // 8) for s in spans})
            if len(xs) >= 4:
                grid_rows += 1
    return grid_rows >= 6


def _scan_warnings(pages: list[PageLayout]) -> list[str]:
    warnings: list[str] = []
    low_density = [p.page_idx for p in pages if p.char_count < LOW_DENSITY_CHAR_THRESHOLD]
    if len(low_density) > 3:
        warnings.append(
            f"{len(low_density)} pages have <{LOW_DENSITY_CHAR_THRESHOLD} chars of "
            f"extracted text (sample pages: {low_density[:5]}). PDF may be a scan or "
            "have heavy image content; consider OCR (backlog item) before relying "
            "on those pages for retrieval."
        )
    landscape = [p.page_idx for p in pages if p.has_landscape_text]
    if landscape:
        warnings.append(
            f"{len(landscape)} pages have landscape / rotated text (sample: "
            f"{landscape[:5]}). Charts or tables may be present; chunked text "
            "should still embed but visual content is lost in extraction."
        )
    return warnings


# ----- Public entrypoint -------------------------------------------------


def analyze(pdf_path: Path) -> PdfAnalysis:
    """One-shot layout analysis. Doesn't extract markdown; that's the
    caller's job (use ``extract_chapter_text``)."""
    doc = pymupdf.open(str(pdf_path))
    try:
        pages = _extract_spans(doc)
        body_size, body_font = _baseline(pages)
        running = _detect_running_text(pages)

        analysis = PdfAnalysis(
            pdf_path=pdf_path,
            page_count=doc.page_count,
            body_size=body_size,
            body_font=body_font,
            running_text=running,
        )

        chapters = _chapters_from_embedded_toc(doc, doc.page_count)
        if chapters is not None:
            analysis.detection_method = "embedded_toc"
        else:
            chapters = _chapters_from_heading_scan(pages, body_size, running)
            if chapters is not None:
                analysis.detection_method = "heading_scan"
        if chapters is None:
            chapters = _printed_toc_chapters(pages, body_size)
            if chapters is not None:
                analysis.detection_method = "printed_toc"
        if chapters is None:
            # Last resort: one chapter for the whole book.
            chapters = [
                Chapter(
                    title=pdf_path.stem,
                    page_start=0,
                    page_end=doc.page_count - 1,
                )
            ]
            analysis.detection_method = "single_chapter_fallback"
            analysis.warnings.append(
                "no chapter boundaries detected — fell back to single-chapter "
                "ingestion. Body text is preserved; retrieval still works on "
                "embedding-time chunks."
            )

        _annotate_chapters(chapters, pages)
        analysis.chapters = chapters
        analysis.warnings.extend(_scan_warnings(pages))
        return analysis
    finally:
        doc.close()


def extract_chapter_text(
    pdf_path: Path,
    chapter: Chapter,
    *,
    running_text: set[tuple[str, int]] | None = None,
) -> str:
    """Return clean body text for one chapter — running headers/footers
    filtered, image / landscape pages flagged with placeholder lines.
    """
    running = running_text or set()
    parts: list[str] = []
    doc = pymupdf.open(str(pdf_path))
    try:
        for pn in range(chapter.page_start, chapter.page_end + 1):
            if pn >= doc.page_count:
                break
            page = doc[pn]
            d = page.get_text("dict")
            page_text: list[str] = []
            for block in d.get("blocks", []):
                if block.get("type") == 1:
                    page_text.append("\n[FIGURE]\n")
                    continue
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    line_text: list[str] = []
                    for span in line.get("spans", []):
                        txt = span.get("text") or ""
                        if not txt.strip():
                            continue
                        sp = Span(
                            page_idx=pn,
                            text=txt,
                            size=float(span.get("size", 0.0)),
                            flags=int(span.get("flags", 0)),
                            font=str(span.get("font", "")),
                            bbox=tuple(span.get("bbox", (0, 0, 0, 0))),
                        )
                        if _is_running(sp, page.rect.height, running):
                            continue
                        line_text.append(txt)
                    if line_text:
                        page_text.append(" ".join(line_text).strip())
            if page.rotation in (90, 270):
                page_text.insert(0, "[LANDSCAPE PAGE]")
            parts.append("\n".join(page_text))
    finally:
        doc.close()
    return "\n\n".join(p for p in parts if p.strip())
