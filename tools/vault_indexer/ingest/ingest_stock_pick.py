"""Click-Capital Stock-Pick PDF → one structured markdown note per pick.

Newsletter author: Jared Mann / ClickCapital.io. Fixed ~9-page template
(see ``Newsletters/click-capital/_INGEST_SPEC.md`` for the canonical
shape).

Two modes:
  • ``--pdf <path>``   single file
  • ``--inbox <dir>``  process every ``*.pdf`` in dir, move to
                       ``<dir>/processed/`` after success, to
                       ``<dir>/_unsupported/`` if shape-check fails

Idempotent on ``source_sha256``. Writes a sibling hypothesis-candidate
file with pre-filled invalidator suggestions for the operator to review.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import re
import shutil
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import pymupdf  # type: ignore

from .common import slug, write_note
from ..config import CONFIG

logger = logging.getLogger(__name__)

INGEST_SPEC_VERSION = 1
AUTHOR_SLUG = "click-capital"
REL_DIR = f"Newsletters/{AUTHOR_SLUG}"
CANDIDATE_DIR = f"{REL_DIR}/_hypothesis_candidates"

# ---------------------------------------------------------------------------
# Shape detection — "is this actually a Click-Capital Stock Pick PDF?"
# ---------------------------------------------------------------------------


@dataclass
class _CoverFacts:
    pick_number: int
    company_name: str
    published_at: datetime.date


@dataclass
class _FactBox:
    ticker: str
    company_name: str
    hq_country: str
    hq_city: Optional[str]
    industry: str
    market_cap_usd_m: Optional[float]
    price_at_pub_usd: Optional[float]
    chart_as_of_utc: Optional[str]


@dataclass
class _Bullet:
    name: str
    body: str


@dataclass
class _ParsedPick:
    cover: _CoverFacts
    fact_box: _FactBox
    about: str
    external_website: Optional[str]
    external_presentation_url: Optional[str]
    thesis_pillars: list[_Bullet] = field(default_factory=list)
    financials: list[_Bullet] = field(default_factory=list)
    financials_extracted: dict = field(default_factory=dict)
    technical_setup: str = ""
    risks: list[_Bullet] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Regex anchors
# ---------------------------------------------------------------------------

RE_PICK_NUMBER = re.compile(r"Stock\s+Pick\s+#\s*(\d+)", re.IGNORECASE)
RE_DATE_LONG = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})\b",
    re.IGNORECASE,
)
RE_TV_CAPTION = re.compile(
    r"Click[-\s]?Capital\s+created\s+with\s+TradingView\.com,\s+"
    r"([A-Za-z]+\s+\d{1,2},\s+\d{4})\s+(\d{1,2}:\d{2})\s+UTC([+\-]\d{1,2})"
)
RE_KV_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?):\s+(.+?)\s*$")
RE_BULLET = re.compile(r"^\s*([A-Z][A-Za-z .&/-]+?)\s+[—\-–]\s+(.+)$")

MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}

SECTION_TITLES = {
    "about": "About the Company",
    "why": "Why Do I Like Them?",
    "numbers": "What Are Their Latest Numbers?",
    "technical": "Technical Analysis of the Chart",
    "risks": "What Are The Risks?",
    "summary": "Summary",
}

# Industry → vault tag mapping. Deterministic, no LLM.
INDUSTRY_TAG_MAP: dict[str, list[str]] = {
    "solar energy": ["energy"],
    "energy": ["energy"],
    "oil": ["energy"],
    "gas": ["energy"],
    "uranium": ["energy"],
    "software": ["software_durability"],
    "saas": ["software_durability"],
    "semiconductor": [],
    "bank": ["credit_cycle"],
    "insurance": ["credit_cycle"],
    "real estate": ["valuations"],
    "reit": ["valuations"],
    "bitcoin": ["btc"],
    "crypto": ["btc"],
}


def _industry_tags(industry: str) -> list[str]:
    low = industry.lower()
    for key, tags in INDUSTRY_TAG_MAP.items():
        if key in low:
            return list(tags)
    return []


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------


def _page_texts(pdf_path: Path) -> list[str]:
    """Return raw text per page. Uses pymupdf 'text' mode."""
    with pymupdf.open(str(pdf_path)) as doc:
        return [p.get_text("text") for p in doc]


def _is_clickcapital_shape(pages: list[str]) -> tuple[bool, str]:
    """Cheap shape check. Returns (ok, reason)."""
    if not (8 <= len(pages) <= 10):
        return False, f"page count {len(pages)} not in [8,10]"
    if not RE_PICK_NUMBER.search(pages[0]):
        return False, "no 'Stock Pick #N' on cover"
    # ClickCapital sign-off appears on summary page.
    if not any("ClickCapital.io" in p or "Click Capital" in p for p in pages):
        return False, "no ClickCapital sign-off"
    return True, ""


def _parse_cover(text: str) -> _CoverFacts:
    """Cover page has: 'Stock Pick #N\\n<Company>\\n<DD<sfx> Month YYYY>'."""
    m_pick = RE_PICK_NUMBER.search(text)
    if not m_pick:
        raise ValueError("cover: no Stock Pick number")
    pick_number = int(m_pick.group(1))

    m_date = RE_DATE_LONG.search(text)
    if not m_date:
        raise ValueError("cover: no date")
    day, month_name, year = m_date.groups()
    month = MONTHS[month_name.lower()]
    published_at = datetime.date(int(year), month, int(day))

    # Company name = the line between the Stock Pick # line and the date.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    pick_idx = next(
        (i for i, ln in enumerate(lines) if RE_PICK_NUMBER.search(ln)), None
    )
    date_idx = next(
        (i for i, ln in enumerate(lines) if RE_DATE_LONG.search(ln)), None
    )
    company_name = ""
    if pick_idx is not None and date_idx is not None and date_idx > pick_idx + 1:
        company_name = lines[pick_idx + 1]
    if not company_name:
        company_name = "Unknown"

    return _CoverFacts(
        pick_number=pick_number,
        company_name=company_name,
        published_at=published_at,
    )


def _parse_money_to_usd_m(raw: str) -> Optional[float]:
    """'542 Million' / '$14.79' / '$427.4 million' → float in USD millions
    (or raw dollars for share prices, see caller).
    """
    s = raw.replace(",", "").replace("$", "").strip()
    m = re.match(r"([\d.]+)\s*([a-zA-Z]*)", s)
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2).lower()
    if unit.startswith("m"):  # 'million' or 'm'
        return n
    if unit.startswith("b"):  # 'billion'
        return n * 1_000
    return n  # bare number (e.g. share price)


_FACT_KEYS = (
    "company",
    "ticker",
    "headquarters",
    "industry",
    "market cap",
    "current price",
)


def _parse_fact_box(text: str, company_default: str) -> _FactBox:
    """Page 2 carries Company / Ticker / HQ / Industry / Market Cap /
    Current Price. Click-Capital's PDF emits each key on its own line
    followed by zero-width-space filler lines, then the value on a
    later line. So we tokenise into non-blank lines (stripping ZWSP)
    and walk: when a line ends with one of the known keys + ':', the
    next non-key line is the value.
    """
    # Strip zero-width spaces, collapse whitespace, keep only non-blank lines.
    lines: list[str] = []
    for raw in text.splitlines():
        cleaned = raw.replace("​", "").strip()
        if cleaned:
            lines.append(cleaned)

    kv: dict[str, str] = {}
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip(":").strip().lower()
        if ln in _FACT_KEYS:
            # Find next line that is NOT one of the known keys.
            for j in range(i + 1, len(lines)):
                nxt_norm = lines[j].rstrip(":").strip().lower()
                if nxt_norm in _FACT_KEYS:
                    break
                # Skip section titles that might appear after the fact box
                # (e.g. "1 Year Stock Price Chart:").
                if "stock price chart" in nxt_norm:
                    break
                kv[ln] = lines[j].strip()
                break
        i += 1

    company = kv.get("company", company_default)
    ticker = kv.get("ticker", "").strip().upper() or "UNKNOWN"
    hq = kv.get("headquarters", "")
    hq_city: Optional[str] = None
    hq_country = hq
    if "," in hq:
        hq_city, hq_country = (p.strip() for p in hq.split(",", 1))
    industry = kv.get("industry", "")

    market_cap_raw = kv.get("market cap", "")
    market_cap = _parse_money_to_usd_m(market_cap_raw) if market_cap_raw else None

    price_raw = kv.get("current price", "")
    price = _parse_money_to_usd_m(price_raw) if price_raw else None

    chart_iso: Optional[str] = None
    m_tv = RE_TV_CAPTION.search(text)
    if m_tv:
        date_part, time_part, tz_part = m_tv.groups()
        try:
            dt = datetime.datetime.strptime(
                f"{date_part} {time_part}", "%B %d, %Y %H:%M"
            )
            chart_iso = dt.strftime("%Y-%m-%dT%H:%M:%S") + f"{int(tz_part):+03d}:00"
        except ValueError:
            chart_iso = None

    return _FactBox(
        ticker=ticker,
        company_name=company,
        hq_country=hq_country or "Unknown",
        hq_city=hq_city,
        industry=industry,
        market_cap_usd_m=market_cap,
        price_at_pub_usd=price,
        chart_as_of_utc=chart_iso,
    )


def _is_disclaimer_page(text: str) -> bool:
    """Page 9 starts with 'Reminder:' / 'Financial Disclaimer:' — never a
    content section. Detect early so it stops aggregating into the last
    real section (summary)."""
    head = text.replace("​", "").strip()[:600].lower()
    if "financial disclaimer" in head:
        return True
    return head.startswith("reminder:") or "reminder: as always" in head


def _strip_page_footer(text: str) -> str:
    """Drop trailing lone-digit lines (page numbers) and ZWSP-only lines."""
    lines = text.replace("​", "").splitlines()
    while lines and (not lines[-1].strip() or (lines[-1].strip().isdigit() and len(lines[-1].strip()) <= 2)):
        lines.pop()
    return "\n".join(lines)


def _split_by_section(pages: list[str]) -> dict[str, str]:
    """Return {section_key: aggregated_text}. Sections start when a page's
    first non-empty content line matches one of SECTION_TITLES values.
    Anything before the first section title is the fact-box / cover bucket.
    Disclaimer page terminates section aggregation.
    """
    sections: dict[str, str] = {}
    current_key: Optional[str] = None
    title_to_key = {title.lower(): key for key, title in SECTION_TITLES.items()}

    def _detect_section_in_page(text: str) -> Optional[str]:
        # The section title is typically the first H1-style line on its page.
        for raw in text.splitlines():
            line = raw.replace("​", "").strip()
            if not line:
                continue
            if line.lower() in title_to_key:
                return title_to_key[line.lower()]
            # No match on first non-empty line → not a section-start page.
            return None
        return None

    for page_text in pages:
        if _is_disclaimer_page(page_text):
            current_key = None
            continue
        page_text = _strip_page_footer(page_text)
        key = _detect_section_in_page(page_text)
        if key is not None:
            current_key = key
            sections.setdefault(current_key, "")
            # Strip the heading line itself from the body.
            body_lines = page_text.splitlines()
            for i, ln in enumerate(body_lines):
                if ln.strip().lower() == SECTION_TITLES[current_key].lower():
                    body_lines = body_lines[i + 1:]
                    break
            sections[current_key] += "\n".join(body_lines) + "\n"
        elif current_key is not None:
            sections[current_key] += page_text + "\n"
    return sections


def _parse_bullets(text: str) -> list[_Bullet]:
    """Bullets shape: each starts with '<Name> — ' on its own line, body
    wraps across following lines, terminator = next bullet start or end of
    section. Click-Capital PDFs use NO blank line between bullets."""
    out: list[_Bullet] = []
    # Strip ZWSP, single-digit footer lines (page numbers), and blank lines.
    cleaned: list[str] = []
    for raw in text.splitlines():
        line = raw.replace("​", "").strip()
        if not line:
            continue
        if line.isdigit() and len(line) <= 2:
            continue
        cleaned.append(line)

    current_name: Optional[str] = None
    current_body: list[str] = []

    def _flush() -> None:
        if current_name and current_body:
            out.append(_Bullet(name=current_name, body=" ".join(current_body).strip()))

    for line in cleaned:
        m = RE_BULLET.match(line)
        if m:
            _flush()
            current_name = m.group(1).strip()
            current_body = [m.group(2).strip()]
        elif current_name:
            current_body.append(line)
    _flush()
    return out


def _extract_financials(text: str) -> dict:
    """Best-effort numeric extraction from page-5 prose. Each match optional."""
    out: dict = {}
    # Revenue: "FY2025 revenue reached $427.4 million, up from $177.0 million"
    m = re.search(
        r"revenue\s+reached\s+\$([\d.]+)\s*million,?\s*up\s+from\s+\$([\d.]+)\s*million",
        text, re.IGNORECASE,
    )
    if m:
        out["revenue_usd_m"] = float(m.group(1))
        out["revenue_prior_usd_m"] = float(m.group(2))

    # Gross profit
    m = re.search(
        r"gross\s+profit\s+jumped\s+to\s+\$([\d.]+)\s*million",
        text, re.IGNORECASE,
    )
    if m:
        out["gross_profit_usd_m"] = float(m.group(1))

    # Gross margin "12.4% to 22.5%"
    m = re.search(r"([\d.]+)%\s+to\s+([\d.]+)%", text)
    if m:
        out["gross_margin_pct_prior"] = float(m.group(1))
        out["gross_margin_pct"] = float(m.group(2))

    # Net income
    m = re.search(r"net\s+income\s+was\s+\$([\d.]+)\s*million", text, re.IGNORECASE)
    if m:
        out["net_income_usd_m"] = float(m.group(1))

    # Adj net income
    m = re.search(
        r"adjusted\s+net\s+income\s+rose\s+sharply\s+to\s+\$([\d.]+)\s*million",
        text, re.IGNORECASE,
    )
    if m:
        out["adj_net_income_usd_m"] = float(m.group(1))

    # Cell shipments (GW)
    m = re.search(r"shipped\s+([\d.]+)\s*GW", text, re.IGNORECASE)
    if m:
        out["cell_shipments_gw"] = float(m.group(1))

    # Module shipments (MW)
    m = re.search(r"shipments?\s+reached\s+([\d.]+)\s*MW", text, re.IGNORECASE)
    if m:
        out["module_shipments_mw"] = float(m.group(1))

    # Guidance "$90–100 million" or "$90-100 million"
    m = re.search(
        r"\$([\d.]+)\s*[\-–—]\s*([\d.]+)\s*million\s+of\s+adjusted\s+net\s+income",
        text, re.IGNORECASE,
    )
    if m:
        out["guidance_adj_ni_low_usd_m"] = float(m.group(1))
        out["guidance_adj_ni_high_usd_m"] = float(m.group(2))

    return out


def _extract_external_links(text: str) -> tuple[Optional[str], Optional[str]]:
    """Page-3 carries 'Learn More at Their Website:' + 'Latest Presentation:'.
    pymupdf 'text' loses click-targets; URLs surface as plain http(s)://… when
    present in the visible label."""
    website = None
    presentation = None
    for line in text.splitlines():
        s = line.replace("​", "").strip()
        if s.startswith(("http://", "https://")):
            if website is None:
                website = s
            else:
                presentation = s
    return website, presentation


def parse_pick(pdf_path: Path) -> _ParsedPick:
    pages = _page_texts(pdf_path)
    ok, reason = _is_clickcapital_shape(pages)
    if not ok:
        raise ValueError(f"shape check failed: {reason}")

    cover = _parse_cover(pages[0])
    fact_box = _parse_fact_box(pages[1], company_default=cover.company_name)
    sections = _split_by_section(pages)

    about_raw = sections.get("about", "")
    website, presentation = _extract_external_links(about_raw)
    # Strip trailing "Learn More at…" + URLs + "Click Here to Read" + footer
    # from the narrative so the markdown 'About' section stays clean.
    about_lines: list[str] = []
    for raw in about_raw.splitlines():
        line = raw.replace("​", "").rstrip()
        low = line.strip().lower()
        if low.startswith(("learn more at", "latest presentation", "click here")):
            break
        about_lines.append(line)
    about = _strip_page_footer("\n".join(about_lines)).strip()

    thesis_pillars = _parse_bullets(sections.get("why", ""))
    financials = _parse_bullets(sections.get("numbers", ""))
    risks = _parse_bullets(sections.get("risks", ""))
    technical_setup = sections.get("technical", "").strip()
    summary = sections.get("summary", "").strip()
    financials_extracted = _extract_financials(sections.get("numbers", ""))

    return _ParsedPick(
        cover=cover,
        fact_box=fact_box,
        about=about,
        external_website=website,
        external_presentation_url=presentation,
        thesis_pillars=thesis_pillars,
        financials=financials,
        financials_extracted=financials_extracted,
        technical_setup=technical_setup,
        risks=risks,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def _render_body(p: _ParsedPick) -> str:
    lines: list[str] = []
    lines.append(f"# Stock Pick #{p.cover.pick_number} — {p.cover.company_name}")
    lines.append("")
    lines.append(f"**Published:** {p.cover.published_at:%d %B %Y}")
    lines.append(
        f"**Ticker:** {p.fact_box.ticker}  |  **Industry:** "
        f"{p.fact_box.industry or '—'}  |  **HQ:** "
        f"{p.fact_box.hq_city + ', ' if p.fact_box.hq_city else ''}"
        f"{p.fact_box.hq_country}"
    )
    cap = (
        f"${p.fact_box.market_cap_usd_m:.0f}M"
        if p.fact_box.market_cap_usd_m is not None
        else "—"
    )
    price = (
        f"${p.fact_box.price_at_pub_usd:.2f}"
        if p.fact_box.price_at_pub_usd is not None
        else "—"
    )
    lines.append(
        f"**Market cap:** {cap}  |  **Price at publication:** {price}"
    )
    lines.append("")

    if p.about:
        lines += ["## About the company", "", p.about.strip(), ""]
    if p.external_website:
        lines += [f"Website: <{p.external_website}>"]
    if p.external_presentation_url:
        lines += [f"Investor presentation: <{p.external_presentation_url}>"]
    if p.external_website or p.external_presentation_url:
        lines.append("")

    if p.thesis_pillars:
        lines += ["## Why the author likes them", ""]
        for b in p.thesis_pillars:
            lines.append(f"- **{b.name} —** {b.body}")
        lines.append("")

    if p.financials:
        lines += ["## Latest numbers", ""]
        for b in p.financials:
            lines.append(f"- **{b.name} —** {b.body}")
        lines.append("")

    if p.technical_setup:
        lines += ["## Technical setup", "", p.technical_setup.strip(), ""]

    if p.risks:
        lines += ["## Risks", ""]
        for b in p.risks:
            lines.append(f"- **{b.name} —** {b.body}")
        lines.append("")

    if p.summary:
        lines += ["## Summary", "", p.summary.strip(), ""]

    lines.append("---")
    lines.append("")
    lines.append(
        "*Boilerplate: avg 6-month holding period (range 2 weeks to 2 years), "
        "losses cut early, ~50% of picks expected to be losers, gains from "
        "winners expected to outweigh losers over time.*"
    )
    return "\n".join(lines).rstrip() + "\n"


def _bullets_to_dicts(bs: list[_Bullet]) -> list[dict]:
    return [{"name": b.name, "body": b.body} for b in bs]


def _build_tags(p: _ParsedPick) -> list[str]:
    tags = ["single_name_conviction", "mid_horizon_investing"]
    tags += _industry_tags(p.fact_box.industry)
    risk_names = " ".join(r.name.lower() for r in p.risks)
    if "geopolit" in risk_names or "policy" in risk_names:
        if "geopolitics" not in tags:
            tags.append("geopolitics")
    return tags


def _build_metadata(p: _ParsedPick, pdf_path: Path, sha: str, n_pages: int) -> dict:
    md: dict = {
        "kind": "newsletter",
        "kind_subtype": "stock_pick",
        "author": AUTHOR_SLUG,
        "title": f"Stock Pick #{p.cover.pick_number} — {p.cover.company_name}",
        "pick_number": p.cover.pick_number,
        "ticker": p.fact_box.ticker,
        "company_name": p.fact_box.company_name,
        "hq_country": p.fact_box.hq_country,
        "industry": p.fact_box.industry,
        "market_cap_usd_m": p.fact_box.market_cap_usd_m,
        "price_at_pub_usd": p.fact_box.price_at_pub_usd,
        "published_at": p.cover.published_at.isoformat(),
        "horizon_months": 6,
        "holding_period_min_weeks": 2,
        "holding_period_max_years": 2,
        "expected_loser_pct": 50,
        "ingest_spec_version": INGEST_SPEC_VERSION,
        "source_path": str(pdf_path),
        "source_sha256": sha,
        "source_pdf_pages_total": n_pages,
        "source_pages": [1, n_pages],
        "thesis_pillars": _bullets_to_dicts(p.thesis_pillars),
        "financials": _bullets_to_dicts(p.financials),
        "financials_extracted": p.financials_extracted,
        "risks": _bullets_to_dicts(p.risks),
        "tags": _build_tags(p),
    }
    if p.fact_box.hq_city:
        md["hq_city"] = p.fact_box.hq_city
    if p.fact_box.chart_as_of_utc:
        md["chart_as_of_utc"] = p.fact_box.chart_as_of_utc
    if p.external_website:
        md["external_website"] = p.external_website
    if p.external_presentation_url:
        md["external_presentation_url"] = p.external_presentation_url
    return md


def _candidate_hypothesis(p: _ParsedPick, note_relpath: str) -> dict:
    """Pre-fill a hypothesis candidate for operator review. Operator picks
    1–2 invalidators and POSTs to /v1/hypotheses on the laptop instance."""
    eval_at = p.cover.published_at + datetime.timedelta(days=180)
    margin_floor = None
    if p.financials_extracted.get("gross_margin_pct"):
        # Set the margin-collapse trigger ~4-5pt below current
        margin_floor = max(0.0, p.financials_extracted["gross_margin_pct"] - 4.5)

    invalidators: list[dict] = [
        {
            "clause": "pct_change_since_entry < -25",
            "name": "trailing-stop",
            "derived_from": (
                "Stock Price Risk + Click-Capital's own custom trailing-stop pattern"
            ),
        },
        {
            "clause": "revenue_yoy_qoq < 30",
            "name": "growth-decel",
            "derived_from": "Customer Concentration + Execution Risk",
        },
    ]
    if margin_floor is not None:
        invalidators.append(
            {
                "clause": f"gross_margin_pct < {margin_floor:.1f}",
                "name": "margin-collapse",
                "derived_from": (
                    f"Solar / cyclical margin defence (current "
                    f"{p.financials_extracted['gross_margin_pct']:.1f}% → "
                    f"{margin_floor:.1f}% kills the thesis)"
                ),
            }
        )

    return {
        "statement": (
            f"{p.fact_box.company_name} ({p.fact_box.ticker}): "
            f"thesis per Click-Capital Stock Pick "
            f"#{p.cover.pick_number} ({p.cover.published_at:%Y-%m-%d}). "
            f"Avg 6-month holding expected. See {note_relpath} for full "
            f"thesis pillars, latest numbers, and risks."
        ),
        "tickers": [p.fact_box.ticker],
        "entry_date": p.cover.published_at.isoformat(),
        "eval_at": eval_at.isoformat(),
        "requires_tv_context": False,
        "evidence_pointers": [
            f"{note_relpath}#why-the-author-likes-them",
            f"{note_relpath}#latest-numbers",
            f"{note_relpath}#technical-setup",
        ],
        "suggested_invalidators": invalidators,
        "vault_node_link": note_relpath,
        "notes": (
            "Operator should pick 1-2 invalidators (not all three) to keep "
            "evaluation crisp. POST to /v1/hypotheses on laptop instance; "
            "pass vault_path=<this note path> so hypothesis_node_links "
            "populates and research bundle surfaces the pick verbatim."
        ),
    }


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _sha256_of_file(path: Path, *, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk_size)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _existing_shas(target_dir: Path) -> set[str]:
    if not target_dir.is_dir():
        return set()
    out: set[str] = set()
    for md in target_dir.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(
            r"^source_sha256:\s*['\"]?([0-9a-f]{64})['\"]?\s*$",
            text, re.MULTILINE,
        )
        if m:
            out.add(m.group(1))
    return out


def _ping_reload(url: Optional[str]) -> None:
    if not url:
        return
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("indexer reload ping → %d", resp.status)
    except Exception as e:  # noqa: BLE001
        logger.warning("indexer reload ping failed: %s", e)


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------


def ingest_one(
    pdf_path: Path,
    *,
    vault_root: Path,
    reingest: bool = False,
) -> dict:
    if not pdf_path.exists():
        return {"pdf": str(pdf_path), "error": "not found"}

    sha = _sha256_of_file(pdf_path)
    target_dir = vault_root / REL_DIR
    seen = _existing_shas(target_dir)
    if sha in seen and not reingest:
        return {"pdf": str(pdf_path), "skipped": "already-ingested", "sha": sha}

    try:
        parsed = parse_pick(pdf_path)
    except Exception as e:  # noqa: BLE001
        return {"pdf": str(pdf_path), "error": f"parse: {e}"}

    n_pages = len(_page_texts(pdf_path))
    metadata = _build_metadata(parsed, pdf_path, sha, n_pages)

    filename = (
        f"{parsed.cover.published_at.isoformat()}"
        f"-stock-pick-{parsed.cover.pick_number:03d}"
        f"-{slug(parsed.fact_box.ticker)}.md"
    )

    note_path = write_note(
        vault_root=vault_root,
        rel_dir=REL_DIR,
        filename=filename,
        body=_render_body(parsed),
        metadata=metadata,
    )
    note_relpath = str(note_path.relative_to(vault_root))

    candidate = _candidate_hypothesis(parsed, note_relpath)
    candidate_dir = vault_root / CANDIDATE_DIR
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_file = candidate_dir / (
        f"{parsed.cover.published_at.isoformat()}"
        f"-{slug(parsed.fact_box.ticker)}.json"
    )
    candidate_file.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")

    return {
        "pdf": str(pdf_path),
        "ticker": parsed.fact_box.ticker,
        "pick_number": parsed.cover.pick_number,
        "published_at": parsed.cover.published_at.isoformat(),
        "note": note_relpath,
        "hypothesis_candidate": str(candidate_file.relative_to(vault_root)),
        "sha": sha,
    }


def ingest_inbox(inbox_dir: Path, *, vault_root: Path, reingest: bool) -> list[dict]:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    processed_dir = inbox_dir / "processed"
    unsupported_dir = inbox_dir / "_unsupported"
    processed_dir.mkdir(exist_ok=True)
    unsupported_dir.mkdir(exist_ok=True)

    results: list[dict] = []
    for pdf in sorted(inbox_dir.glob("*.pdf")):
        result = ingest_one(pdf, vault_root=vault_root, reingest=reingest)
        results.append(result)
        if "error" in result:
            target = unsupported_dir / pdf.name
            shutil.move(str(pdf), str(target))
            logger.warning("moved unsupported %s → %s", pdf.name, target)
        elif "skipped" not in result:
            target = processed_dir / pdf.name
            shutil.move(str(pdf), str(target))
            logger.info("processed %s → %s", pdf.name, target)
    return results


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", help="Single Click-Capital stock-pick PDF.")
    src.add_argument(
        "--inbox",
        help="Folder; process every *.pdf inside, then move to processed/.",
    )
    ap.add_argument(
        "--reingest",
        action="store_true",
        help="Reprocess even when source_sha256 is already present.",
    )
    ap.add_argument(
        "--reload-url",
        default=None,
        help="POST to this URL after writing notes (e.g. http://127.0.0.1:8001/reload).",
    )
    ap.add_argument(
        "--vault-root",
        default=None,
        help="Override CONFIG.vault_path for testing.",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    vault_root = Path(args.vault_root).expanduser() if args.vault_root else CONFIG.vault_path

    if args.pdf:
        results = [ingest_one(Path(args.pdf).expanduser(), vault_root=vault_root, reingest=args.reingest)]
    else:
        results = ingest_inbox(Path(args.inbox).expanduser(), vault_root=vault_root, reingest=args.reingest)

    written = sum(1 for r in results if "note" in r)
    if written:
        _ping_reload(args.reload_url)

    print(json.dumps(results, indent=2))
    return 0 if all("error" not in r for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
