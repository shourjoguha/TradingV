"""CLI for querying The Street snapshots.

Walks ``<vault>/The Street/snapshots/<date>/`` and answers ticker, tier,
politician, and snapshot-listing queries against the markdown writeups +
TSV/JSON in ``<vault>/The Street/data/<date>/``.

Read-only. The vault-indexer (port 8001) handles semantic retrieval; this
CLI is for direct lookups when an exact ticker / politician / tier is known.

Usage::

    python -m tools.the_street.query --ticker META
    python -m tools.the_street.query --tier 1
    python -m tools.the_street.query --tier 2 --date 2026-05-08
    python -m tools.the_street.query --politician "Cleo Fields"
    python -m tools.the_street.query --list-snapshots
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

DEFAULT_VAULT = Path(
    os.environ.get("VAULT_PATH", str(Path.home() / "Documents" / "knowledge-vault"))
)
FOLDER_NAME = "The Street"


@dataclass(frozen=True)
class SnapshotDir:
    date: str
    writeup_dir: Path
    data_dir: Path

    @property
    def aggregate_tsv(self) -> Path:
        return self.data_dir / "multi-channel-tickers.tsv"


def _street_root(vault: Path) -> Path:
    return vault / FOLDER_NAME


def list_snapshots(vault: Path = DEFAULT_VAULT) -> list[SnapshotDir]:
    root = _street_root(vault)
    snaps_dir = root / "snapshots"
    data_root = root / "data"
    if not snaps_dir.is_dir():
        return []
    out: list[SnapshotDir] = []
    for child in sorted(snaps_dir.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        out.append(
            SnapshotDir(
                date=child.name,
                writeup_dir=child,
                data_dir=data_root / child.name,
            )
        )
    return out


def latest_snapshot(vault: Path = DEFAULT_VAULT) -> Optional[SnapshotDir]:
    snaps = list_snapshots(vault)
    return snaps[0] if snaps else None


def _resolve_snapshot(vault: Path, date: Optional[str]) -> Optional[SnapshotDir]:
    if date is None:
        return latest_snapshot(vault)
    snaps = list_snapshots(vault)
    for s in snaps:
        if s.date == date:
            return s
    return None


def _read_aggregate_rows(snapshot: SnapshotDir) -> list[dict[str, str]]:
    if not snapshot.aggregate_tsv.exists():
        return []
    with snapshot.aggregate_tsv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return list(reader)


def find_ticker(ticker: str, vault: Path = DEFAULT_VAULT) -> list[dict[str, object]]:
    """Return per-snapshot detail for ``ticker`` across every snapshot."""
    target = ticker.strip().upper()
    out: list[dict[str, object]] = []
    for snap in list_snapshots(vault):
        rows = _read_aggregate_rows(snap)
        for row in rows:
            if row.get("Ticker", "").strip().upper() != target:
                continue
            out.append(
                {
                    "date": snap.date,
                    "channels": int(row.get("Channels", "0") or 0),
                    "total_signals": int(row.get("TotalSignals", "0") or 0),
                    "billionaires": int(row.get("Billionaires", "0") or 0),
                    "trailblazers": int(row.get("Trailblazers", "0") or 0),
                    "insiders": int(row.get("Insiders", "0") or 0),
                    "politicians": int(row.get("Politicians", "0") or 0),
                    "options_bullish": int(row.get("Options-Bullish", "0") or 0),
                    "etf": row.get("ETF?", "") == "Y",
                    "notable": row.get("Notable", ""),
                    "writeup_dir": str(snap.writeup_dir),
                }
            )
    return out


def list_tier(
    tier: int, snapshot: SnapshotDir, *, exclude_etfs: bool = True
) -> list[dict[str, object]]:
    """Return tickers at the given tier for one snapshot."""
    if tier not in (1, 2, 3):
        raise ValueError(f"tier must be 1, 2, or 3 — got {tier!r}")
    rows = _read_aggregate_rows(snapshot)
    out: list[dict[str, object]] = []
    for row in rows:
        if exclude_etfs and row.get("ETF?", "") == "Y":
            continue
        try:
            channels = int(row.get("Channels", "0") or 0)
            tb = int(row.get("Trailblazers", "0") or 0)
        except ValueError:
            continue
        if tier == 1 and channels >= 4:
            in_tier = True
        elif tier == 2 and channels == 3:
            in_tier = True
        elif tier == 3 and channels == 2 and tb >= 5:
            in_tier = True
        else:
            in_tier = False
        if in_tier:
            out.append(
                {
                    "ticker": row.get("Ticker", ""),
                    "channels": channels,
                    "total_signals": int(row.get("TotalSignals", "0") or 0),
                    "billionaires": int(row.get("Billionaires", "0") or 0),
                    "trailblazers": tb,
                    "insiders": int(row.get("Insiders", "0") or 0),
                    "politicians": int(row.get("Politicians", "0") or 0),
                    "options_bullish": int(row.get("Options-Bullish", "0") or 0),
                    "notable": row.get("Notable", ""),
                }
            )
    return out


def find_politician(
    name: str, vault: Path = DEFAULT_VAULT
) -> list[dict[str, object]]:
    """Return all politician disclosures for the given name across snapshots."""
    target = name.strip().lower()
    out: list[dict[str, object]] = []
    for snap in list_snapshots(vault):
        pol_tsv = snap.data_dir / "politicians.tsv"
        if not pol_tsv.exists():
            continue
        with pol_tsv.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter="\t")
            for row in reader:
                if len(row) < 11:
                    continue
                disclosed, traded, ticker, company, _age, _fv, member, *rest = row
                if member.strip().lower() != target:
                    continue
                out.append(
                    {
                        "snapshot_date": snap.date,
                        "ticker": ticker,
                        "company": company,
                        "traded": traded,
                        "disclosed": disclosed,
                        "value_range": row[10] if len(row) > 10 else "",
                        "fv": _fv,
                    }
                )
    return out


def _fmt_ticker_row(d: dict[str, object]) -> str:
    return (
        f"  {d['date']:<12} ch={d['channels']} tot={d['total_signals']:>3}"
        f"  Bil={d['billionaires']} TB={d['trailblazers']:>2} Ins={d['insiders']}"
        f"  Pol={d['politicians']} Opt={d['options_bullish']}"
        + (" [ETF]" if d.get("etf") else "")
    )


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="tools.the_street.query")
    p.add_argument(
        "--vault",
        default=str(DEFAULT_VAULT),
        help=f"Vault root (default: {DEFAULT_VAULT})",
    )
    p.add_argument("--ticker", help="Lookup ticker across all snapshots.")
    p.add_argument(
        "--tier", type=int, choices=[1, 2, 3], help="List tickers at this tier."
    )
    p.add_argument(
        "--include-etfs",
        action="store_true",
        help="Include ETFs in tier listing (excluded by default).",
    )
    p.add_argument(
        "--date",
        help="Snapshot date (YYYY-MM-DD); defaults to latest.",
    )
    p.add_argument("--politician", help="Lookup politician name across snapshots.")
    p.add_argument(
        "--list-snapshots", action="store_true", help="List available snapshots."
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit machine-readable JSON instead of plain text.",
    )
    args = p.parse_args(argv)
    vault = Path(args.vault)

    if args.list_snapshots:
        snaps = list_snapshots(vault)
        if args.as_json:
            json.dump(
                [{"date": s.date, "writeup_dir": str(s.writeup_dir)} for s in snaps],
                sys.stdout,
                indent=2,
            )
            sys.stdout.write("\n")
        else:
            if not snaps:
                print(f"(no snapshots under {vault / FOLDER_NAME / 'snapshots'})")
            for s in snaps:
                print(f"{s.date}  {s.writeup_dir}")
        return 0

    if args.ticker:
        rows = find_ticker(args.ticker, vault)
        if args.as_json:
            json.dump(rows, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0
        if not rows:
            print(f"(ticker {args.ticker.upper()} not found in any snapshot)")
            return 1
        print(f"{args.ticker.upper()} — {len(rows)} snapshot(s):")
        for r in rows:
            print(_fmt_ticker_row(r))
            if r.get("notable"):
                print(f"      {r['notable']}")
        return 0

    if args.tier is not None:
        snap = _resolve_snapshot(vault, args.date)
        if snap is None:
            print(
                f"(no snapshot for date={args.date or 'latest'}, vault={vault})",
                file=sys.stderr,
            )
            return 1
        rows = list_tier(args.tier, snap, exclude_etfs=not args.include_etfs)
        if args.as_json:
            json.dump(
                {"date": snap.date, "tier": args.tier, "rows": rows},
                sys.stdout,
                indent=2,
            )
            sys.stdout.write("\n")
            return 0
        print(f"Tier {args.tier} — snapshot {snap.date} ({len(rows)} rows)")
        for r in rows:
            print(
                f"  {str(r['ticker']):<8} ch={r['channels']} tot={r['total_signals']:>3}"
                f"  Bil={r['billionaires']} TB={r['trailblazers']:>2}"
                f" Ins={r['insiders']} Pol={r['politicians']}"
                f" Opt={r['options_bullish']}"
            )
        return 0

    if args.politician:
        rows = find_politician(args.politician, vault)
        if args.as_json:
            json.dump(rows, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0
        if not rows:
            print(f"(politician {args.politician!r} not found)")
            return 1
        print(f"{args.politician} — {len(rows)} disclosure(s):")
        for r in rows:
            print(
                f"  {r['snapshot_date']}  {r['ticker']:<6} traded={r['traded']}"
                f" disclosed={r['disclosed']}  {r['value_range']}"
            )
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
