#!/usr/bin/env python3
"""Retrieval baseline capture (retrieval-depth-and-debiasing-program, Phase 0).

Runs a fixed finance query set through the CURRENT fast-path retrieval and
snapshots, per query, the eligible-vs-surfaced delta (via the retrieval_log).
The snapshot is the "before" baseline that Phase 1 compares deep mode against
to quantify the recall gain.

Operator-run, on the laptop, against the live finance cache DB (needs the
bge-large model + populated vault_chunk_vec). Pure-Python retrieval — no LLM,
no API, no billing.

Usage:
    python scripts/retrieval_eval.py \
        --db-path ~/Documents/knowledge-vault/.indexer/cache-finance.db \
        --out .eval/retrieval-baseline-finance.json

If --db-path is omitted, falls back to the indexer CONFIG.db_path.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

# A small, representative finance query set spanning the corpus's content
# kinds (theses, filings, macro, single-name). Stable across runs so the
# fast-vs-deep comparison is apples-to-apples. Grow deliberately, not ad hoc.
DEFAULT_FINANCE_QUERIES = [
    "is the Fed done hiking",
    "NVDA data center demand durability",
    "recession probability yield curve",
    "AAPL services margin trajectory",
    "energy sector capital discipline",
    "commercial real estate regional bank exposure",
    "semiconductor cycle inventory correction",
    "consumer credit delinquency trend",
    "dollar strength emerging markets",
    "AI capex sustainability hyperscalers",
    "small cap valuation vs large cap",
    "credit spreads high yield default cycle",
]


def capture(db_path: Path, queries: list[str], k: int = 8) -> dict:
    """Run each query in fast mode and harvest its retrieval_log record."""
    # Imported lazily so `--help` and unit tests don't pay the model-load cost.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.vault_indexer import cache, retrieval_log, search
    from tools.vault_indexer.config import CONFIG

    con = cache.init(db_path, CONFIG.embedding_dim)
    retrieval_log.ensure_schema(con)

    records: list[dict] = []
    for q in queries:
        results = search.search(con, q, k=k, mode="fast", log=True)
        # Pull the row we just wrote (newest) to capture eligible/dropped.
        latest = retrieval_log.recent(con, limit=1)
        rec = latest[0] if latest else {}
        records.append(
            {
                "query": q,
                "surfaced_count": len(results),
                "eligible_count": rec.get("eligible_count"),
                "dropped_count": len(rec.get("dropped", [])),
                "surfaced": [
                    {"path": r.get("path"), "ord": r.get("ord"),
                     "score": r.get("score")}
                    for r in results
                ],
                "dropped": rec.get("dropped", []),
            }
        )
    return {
        "captured_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "mode": "fast",
        "domain": CONFIG.domain,
        "k": k,
        "db_path": str(db_path),
        "query_count": len(queries),
        "records": records,
    }


def compare(db_path: Path, queries: list[str], fast_k: int = 8) -> dict:
    """Run BOTH fast and deep per query; report the recall delta.

    This is the Phase-1 gate probe: it surfaces, per query, the paths deep mode
    found that the fast path dropped (``deep_only``) — the concrete recall save
    — plus what deep rescued from its own pruned set. Operator-run on the
    laptop (needs the bge model + populated finance cache DB).
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.vault_indexer import cache, graph_search, search
    from tools.vault_indexer.config import CONFIG

    con = cache.init(db_path, CONFIG.embedding_dim)

    records: list[dict] = []
    totals = {"fast_surfaced": 0, "deep_surfaced": 0, "deep_only": 0,
              "deep_pruned": 0}
    for q in queries:
        fast = search.search(con, q, k=fast_k, mode="fast", log=False)
        deep = graph_search.deep_search(con, q, log=False)
        fast_paths = {r.get("path") for r in fast}
        deep_paths = {r.get("path") for r in deep["results"]}
        deep_only = sorted(deep_paths - fast_paths)
        records.append({
            "query": q,
            "fast_surfaced": sorted(fast_paths),
            "deep_surfaced_count": len(deep_paths),
            "deep_only": deep_only,                 # recall save vs fast
            "deep_only_count": len(deep_only),
            "hops_used": deep.get("hops_used"),
            "candidates_per_hop": deep.get("candidates_per_hop"),
            "deep_pruned_count": len(deep.get("pruned", [])),
        })
        totals["fast_surfaced"] += len(fast_paths)
        totals["deep_surfaced"] += len(deep_paths)
        totals["deep_only"] += len(deep_only)
        totals["deep_pruned"] += len(deep.get("pruned", []))
    return {
        "captured_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "mode": "compare",
        "domain": CONFIG.domain,
        "fast_k": fast_k,
        "db_path": str(db_path),
        "query_count": len(queries),
        "totals": totals,
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", type=Path, default=None)
    ap.add_argument(
        "--out", type=Path,
        default=Path(".eval/retrieval-baseline-finance.json"),
    )
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument(
        "--mode", choices=["fast", "compare"], default="fast",
        help="'fast' captures the baseline; 'compare' runs fast+deep and "
             "reports the recall delta (Phase-1 gate probe).",
    )
    args = ap.parse_args(argv)

    db_path = args.db_path
    if db_path is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from tools.vault_indexer.config import CONFIG
        db_path = CONFIG.db_path

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "compare":
        snapshot = compare(db_path, DEFAULT_FINANCE_QUERIES, fast_k=args.k)
        args.out.write_text(json.dumps(snapshot, indent=2))
        t = snapshot["totals"]
        print(
            f"compare → {args.out}\n"
            f"  fast surfaced (total) : {t['fast_surfaced']}\n"
            f"  deep surfaced (total) : {t['deep_surfaced']}\n"
            f"  deep-only recall save : {t['deep_only']} paths fast dropped\n"
            f"  deep pruned (logged)  : {t['deep_pruned']} (each w/ reason)"
        )
        return 0

    snapshot = capture(db_path, DEFAULT_FINANCE_QUERIES, k=args.k)
    args.out.write_text(json.dumps(snapshot, indent=2))
    total_dropped = sum(r["dropped_count"] for r in snapshot["records"])
    print(
        f"baseline → {args.out}  "
        f"({snapshot['query_count']} queries, "
        f"{total_dropped} eligible-but-dropped candidates logged)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
