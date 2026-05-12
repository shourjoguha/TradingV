"""SEC EDGAR ingestion — free regulatory source for filings + insider trades.

For each ticker (or CIK), poll the EDGAR Atom feed for new filings and
write each as a markdown file into ``Filings/<ticker>/``. Idempotent on
``accession_number`` — re-running won't duplicate.

Form types supported in v1:
  • 8-K   — material event (earnings press release, M&A, guidance)
  • 10-Q  — quarterly report
  • 10-K  — annual report

Form 4 (insider trades) and 13F-HR (fund holdings) are deliberately
deferred — both have structured XBRL/XML payloads better served by a
dedicated parser. See ``.claude/tech_debt.md`` for the upgrade path.

Usage::

    # Ingest the last 90 days of 8-Ks and 10-Qs for one ticker.
    python -m tools.vault_indexer.ingest.ingest_edgar --ticker AAPL

    # Backfill since a specific date with a custom form-type list.
    python -m tools.vault_indexer.ingest.ingest_edgar \\
        --ticker META --since 2024-01-01 --form-types 8-K,10-Q,10-K

    # Bulk poll every ticker on the watchlist.
    python -m tools.vault_indexer.ingest.ingest_edgar --watchlist

Required env: ``EDGAR_USER_AGENT`` (SEC requires polite identification,
e.g. ``"trader-app/1.0 you@example.com"``). Without it the request returns
403. Polite rate-limit: max 10 requests/second; we self-throttle to 5/s.
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional
from xml.etree import ElementTree as ET

from .common import slug, write_note
from ..config import CONFIG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EDGAR_BASE = "https://www.sec.gov"
COMPANY_TICKERS_URL = f"{EDGAR_BASE}/files/company_tickers.json"
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

DEFAULT_FORM_TYPES = ("8-K", "10-Q", "10-K")
SUPPORTED_FORM_TYPES = frozenset({"8-K", "10-Q", "10-K"})

# Cached ticker→CIK map. EDGAR publishes ~10 MB JSON; we mirror it under
# ``<vault>/.indexer/edgar_company_tickers.json`` and refresh weekly.
_TICKER_CACHE_TTL_SECONDS = 7 * 24 * 3600

# Politeness: SEC asks for ≤10 req/s. We hold to ≤5 to leave headroom.
_THROTTLE_SECONDS = 0.2


# ---------------------------------------------------------------------------
# HTTP helpers (urllib so we don't add a runtime dep)
# ---------------------------------------------------------------------------

def _user_agent() -> str:
    ua = os.environ.get("EDGAR_USER_AGENT", "").strip()
    if not ua:
        raise RuntimeError(
            "EDGAR_USER_AGENT env var required. SEC mandates polite "
            "identification, e.g. 'trader-app/1.0 you@example.com'."
        )
    return ua


def _http_get(url: str, *, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _user_agent(), "Accept-Encoding": "gzip, deflate"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        encoding = resp.headers.get("Content-Encoding", "")
    if encoding == "gzip":
        import gzip
        raw = gzip.decompress(raw)
    elif encoding == "deflate":
        import zlib
        raw = zlib.decompress(raw)
    time.sleep(_THROTTLE_SECONDS)
    return raw


# ---------------------------------------------------------------------------
# Ticker → CIK resolution
# ---------------------------------------------------------------------------

def _ticker_cache_path() -> Path:
    base = CONFIG.vault_path / ".indexer"
    base.mkdir(parents=True, exist_ok=True)
    return base / "edgar_company_tickers.json"


def _load_or_refresh_ticker_map() -> dict[str, str]:
    """Return ``{TICKER: CIK-zero-padded-10}``. Refreshes from SEC when the
    cached copy is older than the TTL or missing."""
    cache = _ticker_cache_path()
    if cache.exists():
        age = time.time() - cache.stat().st_mtime
        if age < _TICKER_CACHE_TTL_SECONDS:
            return _parse_ticker_json(cache.read_bytes())
    raw = _http_get(COMPANY_TICKERS_URL)
    cache.write_bytes(raw)
    return _parse_ticker_json(raw)


def _parse_ticker_json(raw: bytes) -> dict[str, str]:
    """SEC's company_tickers.json shape:
    ``{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, …}``
    """
    data = json.loads(raw)
    out: dict[str, str] = {}
    for entry in data.values():
        ticker = entry.get("ticker", "").upper().strip()
        cik = entry.get("cik_str")
        if ticker and cik is not None:
            out[ticker] = f"{int(cik):010d}"
    return out


def resolve_cik(ticker: str) -> Optional[str]:
    """Return zero-padded 10-digit CIK for a ticker, or None when unknown.

    Looks up the cached SEC ticker map (auto-refreshes weekly).
    """
    tmap = _load_or_refresh_ticker_map()
    return tmap.get(ticker.upper().strip())


# ---------------------------------------------------------------------------
# Atom feed parsing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FilingEntry:
    accession_number: str           # e.g. "0000320193-26-000005"
    form_type: str                  # "8-K", "10-Q", "10-K"
    filed_at: datetime.date
    title: str
    summary: str
    index_url: str                  # link to filing index page on EDGAR


def _atom_url_for(cik: str, form_type: str, count: int = 40) -> str:
    return (
        f"{EDGAR_BASE}/cgi-bin/browse-edgar?"
        + urllib.parse.urlencode(
            {
                "action": "getcompany",
                "CIK": cik,
                "type": form_type,
                "dateb": "",
                "owner": "include",
                "count": count,
                "output": "atom",
            }
        )
    )


_ACCESSION_RE = re.compile(r"\b(\d{10}-\d{2}-\d{6})\b")


def parse_atom(xml_bytes: bytes) -> list[FilingEntry]:
    """Parse SEC's Atom feed into structured ``FilingEntry`` rows.

    EDGAR's atom feed varies slightly between endpoints; we extract the
    fields we need defensively. Entries we can't parse are skipped (logged
    at debug level, not error — SEC publishes amendments + correspondence
    that lack our expected fields).
    """
    out: list[FilingEntry] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("EDGAR atom parse failed: %s", e)
        return out

    for entry in root.findall("a:entry", ATOM_NS):
        try:
            title_node = entry.find("a:title", ATOM_NS)
            summary_node = entry.find("a:summary", ATOM_NS)
            updated_node = entry.find("a:updated", ATOM_NS)
            link_node = entry.find("a:link", ATOM_NS)
            if title_node is None or updated_node is None or link_node is None:
                continue

            title = (title_node.text or "").strip()
            summary = (summary_node.text or "").strip() if summary_node is not None else ""
            href = link_node.attrib.get("href", "")
            if not href:
                continue

            # SEC titles look like "8-K - Apple Inc. (0000320193) (Filer)".
            form_match = re.match(r"^([0-9A-Z\-/]+)\s*-\s*", title)
            form_type = form_match.group(1).strip() if form_match else ""
            if not form_type:
                continue

            # Accession number is in the summary OR the href.
            acc_match = _ACCESSION_RE.search(summary) or _ACCESSION_RE.search(href)
            if not acc_match:
                continue
            accession = acc_match.group(1)

            filed_iso = (updated_node.text or "").split("T", 1)[0]
            try:
                filed_at = datetime.date.fromisoformat(filed_iso)
            except ValueError:
                continue

            out.append(
                FilingEntry(
                    accession_number=accession,
                    form_type=form_type,
                    filed_at=filed_at,
                    title=title,
                    summary=summary,
                    index_url=href,
                )
            )
        except Exception as e:                             # noqa: BLE001
            logger.debug("skipping atom entry: %s", e)
            continue
    return out


# ---------------------------------------------------------------------------
# Primary document fetch + text extraction
# ---------------------------------------------------------------------------

def _index_json_url(accession: str, cik: str) -> str:
    """EDGAR exposes a JSON manifest of every file in a filing at this path."""
    cleaned = accession.replace("-", "")
    return f"{EDGAR_BASE}/Archives/edgar/data/{int(cik)}/{cleaned}/index.json"


def _primary_doc_url(accession: str, cik: str) -> Optional[str]:
    """Return the URL of the filing's primary document (.htm) or None.

    EDGAR's index.json shape::
        {"directory": {"item": [{"name": "...", "type": "...", "size": ...}, ...]}}

    Strategy: skip SEC's auto-generated ``*-index.htm`` (that's the filing's
    metadata page, not the content) and any ``*-summary.html`` style
    rollups, then pick the first remaining .htm — typically the actual
    primary doc named ``<ticker>-<filing-date>.htm``.
    """
    try:
        raw = _http_get(_index_json_url(accession, cik))
        data = json.loads(raw)
    except Exception as e:                                 # noqa: BLE001
        logger.warning("EDGAR index.json fetch failed for %s: %s", accession, e)
        return None
    items = ((data.get("directory") or {}).get("item")) or []
    htm_files = [
        i
        for i in items
        if i.get("name", "").lower().endswith((".htm", ".html"))
        and not i.get("name", "").lower().endswith(("-index.htm", "-index.html"))
    ]
    if not htm_files:
        return None
    cleaned_acc = accession.replace("-", "")
    return f"{EDGAR_BASE}/Archives/edgar/data/{int(cik)}/{cleaned_acc}/{htm_files[0]['name']}"


def fetch_filing_text(accession: str, cik: str) -> Optional[tuple[str, str]]:
    """Fetch the primary document of a filing and extract title + plain text.

    Returns ``(title, text)`` or ``None`` when the filing can't be retrieved.
    """
    doc_url = _primary_doc_url(accession, cik)
    if not doc_url:
        return None
    try:
        from readability import Document
        from lxml.html import fromstring as parse_html

        raw = _http_get(doc_url)
        doc = Document(raw.decode("utf-8", errors="replace"))
        title = (doc.short_title() or "").strip() or accession
        tree = parse_html(doc.summary())
        text = "\n\n".join(
            p.text_content().strip()
            for p in tree.iter()
            if p.tag in {"p", "blockquote", "li", "h1", "h2", "h3"}
            and p.text_content().strip()
        )
        return title, text
    except Exception as e:                                 # noqa: BLE001
        logger.warning("EDGAR text extraction failed for %s: %s", accession, e)
        return None


# ---------------------------------------------------------------------------
# Vault writer
# ---------------------------------------------------------------------------

def write_filing(
    *,
    vault_root: Path,
    ticker: str,
    cik: str,
    entry: FilingEntry,
    title: str,
    body: str,
) -> Path:
    rel_dir = f"Filings/{ticker.upper()}"
    filename = (
        f"{entry.filed_at.isoformat()}-{slug(entry.form_type)}-"
        f"{slug(entry.accession_number)}.md"
    )
    horizon = 3 if entry.form_type == "8-K" else 12  # 8-Ks stale fast; annuals last
    metadata = {
        "kind": "filing",
        "title": title,
        "ticker": ticker.upper(),
        "cik": cik,
        "form_type": entry.form_type,
        "accession_number": entry.accession_number,
        "filed_at": entry.filed_at.isoformat(),
        "source_url": entry.index_url,
        "horizon_months": horizon,
        "tags": ["filing", entry.form_type.lower(), ticker.upper().lower()],
    }
    return write_note(
        vault_root=vault_root,
        rel_dir=rel_dir,
        filename=filename,
        body=f"# {title}\n\n*{ticker.upper()} · {entry.form_type} · filed {entry.filed_at.isoformat()}*\n\n{body}",
        metadata=metadata,
    )


def _existing_accession_set(vault_root: Path, ticker: str) -> set[str]:
    """Scan the ticker's filings folder for already-ingested accession numbers
    so re-runs are idempotent."""
    folder = vault_root / "Filings" / ticker.upper()
    if not folder.is_dir():
        return set()
    accessions: set[str] = set()
    for md in folder.glob("*.md"):
        m = _ACCESSION_RE.search(md.name)
        if m:
            accessions.add(m.group(1))
    return accessions


# ---------------------------------------------------------------------------
# Per-ticker poll
# ---------------------------------------------------------------------------

def ingest_ticker(
    *,
    ticker: str,
    vault_root: Optional[Path] = None,
    form_types: Iterable[str] = DEFAULT_FORM_TYPES,
    since: Optional[datetime.date] = None,
    max_per_form: int = 10,
) -> dict:
    """Poll EDGAR for one ticker. Returns ``{fetched, written, skipped}``.

    Ingestion is idempotent: filings whose accession number already exists
    in the ticker folder are skipped. Filings older than ``since`` are
    skipped. Form types not in :data:`SUPPORTED_FORM_TYPES` are skipped
    with a warning.
    """
    root = vault_root or CONFIG.vault_path
    ticker_u = ticker.upper().strip()
    cik = resolve_cik(ticker_u)
    if cik is None:
        return {"ticker": ticker_u, "error": "unknown_ticker"}

    seen = _existing_accession_set(root, ticker_u)
    fetched = 0
    written = 0
    skipped = 0
    written_paths: list[str] = []

    for form_type in form_types:
        ft = form_type.upper().strip()
        if ft not in SUPPORTED_FORM_TYPES:
            logger.warning("EDGAR form_type %r not supported in v1; skipping", ft)
            continue
        try:
            atom = _http_get(_atom_url_for(cik, ft, count=max(20, max_per_form * 2)))
        except Exception as e:                             # noqa: BLE001
            logger.warning("EDGAR atom fetch failed (%s %s): %s", ticker_u, ft, e)
            continue
        # Defensive: filter to entries whose form_type matches the requested
        # one. EDGAR's atom occasionally returns adjacent forms (amendments,
        # correspondence) when the URL filter is loose; we only want exact
        # matches per the operator's requested set.
        entries = [e for e in parse_atom(atom) if e.form_type == ft][:max_per_form]
        for entry in entries:
            fetched += 1
            if since and entry.filed_at < since:
                skipped += 1
                continue
            if entry.accession_number in seen:
                skipped += 1
                continue
            text = fetch_filing_text(entry.accession_number, cik)
            if text is None:
                skipped += 1
                continue
            title, body = text
            path = write_filing(
                vault_root=root,
                ticker=ticker_u,
                cik=cik,
                entry=entry,
                title=title,
                body=body,
            )
            written += 1
            written_paths.append(str(path.relative_to(root)))
            seen.add(entry.accession_number)

    return {
        "ticker": ticker_u,
        "cik": cik,
        "fetched": fetched,
        "written": written,
        "skipped": skipped,
        "written_paths": written_paths,
    }


def ingest_tickers(
    tickers: Iterable[str],
    *,
    form_types: Iterable[str] = DEFAULT_FORM_TYPES,
    since: Optional[datetime.date] = None,
    max_per_form: int = 5,
    vault_root: Optional[Path] = None,
) -> list[dict]:
    out: list[dict] = []
    for t in tickers:
        try:
            out.append(
                ingest_ticker(
                    ticker=t,
                    form_types=form_types,
                    since=since,
                    max_per_form=max_per_form,
                    vault_root=vault_root,
                )
            )
        except Exception as e:                             # noqa: BLE001
            logger.exception("EDGAR ingest failed for %s", t)
            out.append({"ticker": t.upper(), "error": str(e)})
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _watchlist_tickers() -> list[str]:
    """Pull the current operational watchlist from the local Postgres.

    Lazily imports SQLAlchemy + the model so the CLI works even on a
    machine without the backend installed (just won't have --watchlist).
    """
    try:
        import asyncio

        from sqlalchemy import select

        from app.core import db as _db
        from app.watchlist.models import WatchlistItem
    except Exception as e:                                 # noqa: BLE001
        logger.warning("--watchlist unavailable (backend imports failed): %s", e)
        return []

    async def _fetch() -> list[str]:
        async with _db.SessionLocal() as session:
            rows = await session.execute(
                select(WatchlistItem.symbol).order_by(WatchlistItem.symbol)
            )
            return [r[0] for r in rows]

    return asyncio.run(_fetch())


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="ingest_edgar")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ticker", help="Single ticker to ingest.")
    src.add_argument("--tickers", help="Comma-separated tickers.")
    src.add_argument(
        "--watchlist",
        action="store_true",
        help="Ingest every symbol on the operational watchlist.",
    )

    ap.add_argument(
        "--form-types",
        default=",".join(DEFAULT_FORM_TYPES),
        help=f"Comma-separated form types. Supported: {sorted(SUPPORTED_FORM_TYPES)}.",
    )
    ap.add_argument("--since", help="ISO date floor for filed_at (e.g. 2024-01-01).")
    ap.add_argument(
        "--max-per-form",
        type=int,
        default=5,
        help="Cap filings ingested per form type per ticker per run.",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.ticker:
        tickers = [args.ticker]
    elif args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = _watchlist_tickers()
        if not tickers:
            print("watchlist empty or unavailable", file=sys.stderr)
            return 1

    since = datetime.date.fromisoformat(args.since) if args.since else None
    form_types = [f.strip() for f in args.form_types.split(",") if f.strip()]

    results = ingest_tickers(
        tickers,
        form_types=form_types,
        since=since,
        max_per_form=args.max_per_form,
    )
    total_written = sum(r.get("written", 0) for r in results)
    total_skipped = sum(r.get("skipped", 0) for r in results)
    for r in results:
        print(r)
    print(f"\nDone. wrote={total_written}, skipped={total_skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
