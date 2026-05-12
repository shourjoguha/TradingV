"""Build per-ticker digests from a snapshot's raw scrape files.

For each snapshot under ``<vault>/The Street/data/<date>/``, parse the
five raw channel files and emit a single ``digests.json`` keyed by
ticker. Each entry collects every channel mention with its supporting
detail — fund names, insider buys with $value/shares/price, politician
disclosures with date+committee+value-range, options sweeps with
premium/conviction.

The frontend's accordion-style ``StreetDigestPanel`` reads this file via
the new ``/v1/the-street/digest/{date}/{ticker}`` endpoint, so the
expand interaction is a single static file read — no upstream API call.

Usage::

    # Build for one snapshot date.
    python -m tools.the_street.build_digests --date 2026-05-08

    # Build for every snapshot in the vault.
    python -m tools.the_street.build_digests --all

    # Force a rebuild even if digests.json is newer than sources.
    python -m tools.the_street.build_digests --date 2026-05-08 --force
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .query import DEFAULT_VAULT, list_snapshots

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-channel parsers — return per-ticker lists of structured rows
# ---------------------------------------------------------------------------

def _parse_fund_json(path: Path) -> dict[str, list[dict]]:
    """Trailblazers / Billionaires share the shape: ``dict[fund_name, list[str]]``
    where each string is ``"TICKER\tCOMPANY\tSTATUS_LABEL"``. Returns
    ``dict[ticker, list[{"fund": str, "company": str, "status": str}]]``.
    """
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = defaultdict(list)
    for fund, rows in raw.items():
        for row in rows:
            parts = row.split("\t")
            if len(parts) < 3:
                continue
            ticker, company, status = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if not ticker:
                continue
            out[ticker.upper()].append(
                {"fund": fund, "company": company, "status": status}
            )
    return dict(out)


def _parse_insiders_tsv(path: Path) -> dict[str, list[dict]]:
    """``date, ticker, company, age, person, title, value, shares, price, sign``."""
    if not path.exists():
        return {}
    out: dict[str, list[dict]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if len(row) < 10:
                continue
            (
                date,
                ticker,
                company,
                _age,
                person,
                title,
                value,
                shares,
                price,
                sign,
            ) = row[:10]
            if not ticker:
                continue
            out[ticker.upper()].append(
                {
                    "date": date,
                    "company": company,
                    "person": person,
                    "title": title,
                    "value": value,
                    "shares": shares,
                    "price": price,
                    "sign": sign,
                }
            )
    return dict(out)


def _parse_politicians_tsv(path: Path) -> dict[str, list[dict]]:
    """``disclosed, traded, ticker, company, age, fv, member, party, district,
    committee, value_range``."""
    if not path.exists():
        return {}
    out: dict[str, list[dict]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if len(row) < 11:
                continue
            (
                disclosed,
                traded,
                ticker,
                company,
                _age,
                fv,
                member,
                party,
                district,
                committee,
                value_range,
            ) = row[:11]
            if not ticker:
                continue
            out[ticker.upper()].append(
                {
                    "traded": traded,
                    "disclosed": disclosed,
                    "company": company,
                    "fv": fv,
                    "member": member,
                    "party": party,
                    "district": district,
                    "committee": committee,
                    "value_range": value_range,
                }
            )
    return dict(out)


def _parse_options_tsv(path: Path) -> dict[str, list[dict]]:
    """``date, ticker, company, age, fv, signal, conviction, contract, premium, ratio``."""
    if not path.exists():
        return {}
    out: dict[str, list[dict]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if len(row) < 10:
                continue
            (
                date,
                ticker,
                company,
                _age,
                fv,
                signal,
                conviction,
                contract,
                premium,
                ratio,
            ) = row[:10]
            if not ticker:
                continue
            out[ticker.upper()].append(
                {
                    "date": date,
                    "company": company,
                    "fv": fv,
                    "signal": signal,
                    "conviction": conviction,
                    "contract": contract,
                    "premium": premium,
                    "ratio": ratio,
                }
            )
    return dict(out)


# ---------------------------------------------------------------------------
# Markdown rendering — what the copy-to-clipboard button emits
# ---------------------------------------------------------------------------

def _render_markdown(ticker: str, snapshot_date: str, entry: dict) -> str:
    """Render a per-ticker digest as a copy-paste-friendly Markdown block."""
    channels = entry["channels"]
    company = entry.get("company") or ""
    out = [f"# {ticker} — {snapshot_date} smart-money snapshot"]
    if company:
        out.append(f"_{company}_")
    out.append("")
    out.append(
        f"**{entry['channel_count']} channels · {entry['total_signals']} total mentions**"
    )
    out.append("")

    bil = channels.get("billionaires") or []
    if bil:
        out.append(f"## Billionaires ({len(bil)})")
        for r in bil:
            line = f"- **{r['fund']}** — {r['status']}"
            if r.get("company") and r["company"] != company:
                line += f" ({r['company']})"
            out.append(line)
        out.append("")

    tb = channels.get("trailblazers") or []
    if tb:
        out.append(f"## Trailblazers ({len(tb)})")
        for r in tb:
            line = f"- **{r['fund']}** — {r['status']}"
            if r.get("company") and r["company"] != company:
                line += f" ({r['company']})"
            out.append(line)
        out.append("")

    ins = channels.get("insiders") or []
    if ins:
        out.append(f"## Insiders ({len(ins)})")
        for r in ins:
            line = (
                f"- {r['date']} — **{r['person']}** ({r['title']}) "
                f"bought {r['value']} ({r['shares']} sh @ {r['price']})"
            )
            out.append(line)
        out.append("")

    pol = channels.get("politicians") or []
    if pol:
        out.append(f"## Politicians ({len(pol)})")
        for r in pol:
            party_dist = " ".join(p for p in [r.get("party"), r.get("district")] if p)
            line = (
                f"- **{r['member']}** ({party_dist}) — {r['value_range']}\n"
                f"  Traded {r['traded']}, disclosed {r['disclosed']}"
            )
            if r.get("committee"):
                line += f" · committee: {r['committee']}"
            if r.get("fv") and r["fv"] not in ("—", "-", ""):
                line += f" · {r['fv']} since trade"
            out.append(line)
        out.append("")

    opt = channels.get("options_bullish") or []
    if opt:
        out.append(f"## Options-Bullish ({len(opt)})")
        for r in opt:
            line = (
                f"- {r['date']} — {r['contract']} — {r['premium']} premium, "
                f"conviction {r['conviction']} ({r['ratio']} vs OI)"
            )
            out.append(line)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

@dataclass
class Digest:
    ticker: str
    company: str = ""
    channel_count: int = 0
    total_signals: int = 0
    channels: dict[str, list[dict]] = field(default_factory=dict)
    markdown: str = ""

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company": self.company,
            "channel_count": self.channel_count,
            "total_signals": self.total_signals,
            "channels": self.channels,
            "markdown": self.markdown,
        }


def build_for_snapshot(date_dir: Path, snapshot_date: str) -> dict[str, Digest]:
    """Parse every channel file under ``date_dir`` and return per-ticker digests."""
    bil = _parse_fund_json(date_dir / "billionaires.json")
    tb = _parse_fund_json(date_dir / "trailblazers.json")
    ins = _parse_insiders_tsv(date_dir / "insiders.tsv")
    pol = _parse_politicians_tsv(date_dir / "politicians.tsv")
    opt = _parse_options_tsv(date_dir / "options_bullish.tsv")

    tickers = (
        set(bil.keys()) | set(tb.keys()) | set(ins.keys()) | set(pol.keys()) | set(opt.keys())
    )
    digests: dict[str, Digest] = {}
    for ticker in sorted(tickers):
        channels: dict[str, list[dict]] = {}
        if ticker in bil:
            channels["billionaires"] = bil[ticker]
        if ticker in tb:
            channels["trailblazers"] = tb[ticker]
        if ticker in ins:
            channels["insiders"] = ins[ticker]
        if ticker in pol:
            channels["politicians"] = pol[ticker]
        if ticker in opt:
            channels["options_bullish"] = opt[ticker]

        # First non-empty company string we see wins.
        company = ""
        for ch_rows in channels.values():
            for r in ch_rows:
                if r.get("company"):
                    company = r["company"]
                    break
            if company:
                break

        d = Digest(
            ticker=ticker,
            company=company,
            channel_count=len(channels),
            total_signals=sum(len(v) for v in channels.values()),
            channels=channels,
        )
        d.markdown = _render_markdown(ticker, snapshot_date, d.to_dict())
        digests[ticker] = d
    return digests


def write_digests(date_dir: Path, snapshot_date: str, digests: dict[str, Digest]) -> Path:
    out_path = date_dir / "digests.json"
    body = {
        "snapshot_date": snapshot_date,
        "generated_at": _now_iso(),
        "tickers": {t: d.to_dict() for t, d in digests.items()},
    }
    out_path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return out_path


def _now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _is_stale(date_dir: Path) -> bool:
    """Return True when digests.json is missing or older than any source."""
    out = date_dir / "digests.json"
    if not out.exists():
        return True
    out_mtime = out.stat().st_mtime
    sources = [
        date_dir / "billionaires.json",
        date_dir / "trailblazers.json",
        date_dir / "insiders.tsv",
        date_dir / "politicians.tsv",
        date_dir / "options_bullish.tsv",
    ]
    for src in sources:
        if src.exists() and src.stat().st_mtime > out_mtime:
            return True
    return False


def build_one(date_dir: Path, snapshot_date: str, *, force: bool) -> Path | None:
    if not force and not _is_stale(date_dir):
        return None
    digests = build_for_snapshot(date_dir, snapshot_date)
    out = write_digests(date_dir, snapshot_date, digests)
    logger.info("wrote %s (%d tickers)", out, len(digests))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.the_street.build_digests")
    parser.add_argument(
        "--vault",
        default=str(DEFAULT_VAULT),
        help=f"Vault root (default {DEFAULT_VAULT}).",
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--date", help="Snapshot date YYYY-MM-DD.")
    grp.add_argument("--all", action="store_true", help="Build every snapshot.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even when digests.json is newer than sources.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    vault = Path(args.vault)

    if args.all:
        snaps = list_snapshots(vault)
    else:
        snaps = [s for s in list_snapshots(vault) if s.date == args.date]
        if not snaps:
            print(f"snapshot {args.date!r} not found in {vault}")
            return 1

    written = 0
    skipped = 0
    for s in snaps:
        out = build_one(s.data_dir, s.date, force=args.force)
        if out is None:
            skipped += 1
        else:
            written += 1
    print(f"built: {written}, skipped (up-to-date): {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
