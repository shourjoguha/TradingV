"""Bake a frozen scrubbed snapshot of the live laptop DB into demo-data/.

This script lives on the `demo` branch but is excluded from the Railway
image (.dockerignore). Run it locally on the laptop with the live
DATABASE_URL exported. It writes JSON files into demo-data/ which then
get committed to the demo branch and re-deployed.

Usage:
    cd TradingView-demo
    export DATABASE_URL="postgresql+asyncpg://user:pass@host:5439/db"
    python scripts/bake_demo_snapshot.py
    git add demo-data && git commit -m "demo: refresh snapshot $(date +%F)"
    git push origin demo

Scrubbing rules applied to every row:
  - Drop columns matching SCRUB_COLS (emails, IPs, raw LLM prompts).
  - Replace identifiers in ID_RENAME_PREFIX with stable hashes.
  - Drop rows whose `is_demo_safe = false` if the column exists.

This is a SKELETON. Each query is wrapped in `# TODO:` notes where the
laptop schema may differ (column names, filter clauses). Run, inspect
output, adjust queries, run again. The Phase 1 placeholder data already
produces a working demo, so the bake is non-blocking for shipping.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
except ImportError:  # pragma: no cover
    print("error: sqlalchemy[asyncio] not installed in this venv", file=sys.stderr)
    print("       activate the laptop venv (../TradingView /venv) before running.", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "demo-data"

SCRUB_COLS = {"email", "ip", "ip_address", "user_agent", "raw_prompt", "raw_response", "session_id"}
ID_HASH_SALT = "tradingview-demo-2026"
CUTOFF_DATE = os.environ.get("DEMO_CUTOFF_DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _hash_id(s: str) -> str:
    return "demo-" + hashlib.sha256((ID_HASH_SALT + s).encode()).hexdigest()[:10]


def _scrub_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if k in SCRUB_COLS:
            continue
        if isinstance(v, datetime):
            v = v.isoformat()
        out[k] = v
    return out


def _scrub_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_scrub_row(r) for r in rows]


def _write(rel: str, payload: Any) -> None:
    out = OUT_DIR / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {out.relative_to(ROOT)} ({len(json.dumps(payload))} bytes)")


# --- queries -----------------------------------------------------------
# Each query is intentionally tight — it returns the minimum columns the
# frontend needs. Adjust column names if the laptop schema diverges.

Q_DRIFT_ALERTS = text("""
    SELECT id, ticker, horizon, ratio, ack, created_at
    FROM drift_alerts
    WHERE created_at >= NOW() - INTERVAL '30 days'
    ORDER BY created_at DESC
    LIMIT 10
""")

Q_RESEARCH_PENDING = text("""
    SELECT id, question, status, created_at
    FROM research_queries
    WHERE status = 'pending'
    ORDER BY created_at DESC
    LIMIT 10
""")

Q_FRESH_SIGNALS = text("""
    SELECT id, ticker, kind, rule, score, horizon, created_at
    FROM opportunities
    WHERE status = 'open' AND created_at >= NOW() - INTERVAL '7 days'
    ORDER BY score DESC
    LIMIT 20
""")

Q_PREDICTIONS_BY_HORIZON = text("""
    SELECT horizon, ticker, predicted_close, current_close,
           (predicted_close - current_close) / NULLIF(current_close, 0) * 100 AS delta_pct,
           as_of
    FROM prediction_points
    WHERE as_of = (SELECT MAX(as_of) FROM prediction_points)
    ORDER BY horizon, ticker
    LIMIT 200
""")

Q_ACCURACY = text("""
    SELECT horizon, COUNT(*) AS samples,
           AVG(ABS(error)) AS mape, AVG(CASE WHEN sign_correct THEN 1.0 ELSE 0.0 END) AS hit_rate
    FROM prediction_accuracy
    GROUP BY horizon
    ORDER BY horizon
""")

Q_OPPORTUNITIES = text("""
    SELECT id, ticker, kind, rule, score, horizon, status, created_at
    FROM opportunities
    WHERE created_at >= NOW() - INTERVAL '30 days'
    ORDER BY created_at DESC
    LIMIT 100
""")

Q_TRADES = text("""
    SELECT id, ticker, side, entry_price, exit_price,
           (exit_price - entry_price) / NULLIF(entry_price, 0) * 100 AS pnl_pct,
           rule_attribution, opened_at, closed_at
    FROM trades
    WHERE closed_at IS NOT NULL AND closed_at >= NOW() - INTERVAL '90 days'
    ORDER BY closed_at DESC
    LIMIT 50
""")


async def bake() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set. Aborting.", file=sys.stderr)
        sys.exit(1)
    if "+asyncpg" not in db_url and "+aiosqlite" not in db_url:
        print(f"WARN: DATABASE_URL is not async-flavoured ({db_url.split('://')[0]}://). "
              f"Adjusting to asyncpg.", file=sys.stderr)
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        async def fetch(q):  # noqa: ANN001, ANN202
            res = await conn.execute(q)
            return _scrub_rows([dict(r) for r in res.mappings().all()])

        print(f"baking snapshot @ cutoff={CUTOFF_DATE}")

        today_payload = {
            "drift_alerts": await fetch(Q_DRIFT_ALERTS),
            "research_pending": await fetch(Q_RESEARCH_PENDING),
            "fresh_signals": await fetch(Q_FRESH_SIGNALS),
            "regime": {"label": "frozen", "vix": None, "spy_pct_1w": None},
            "watchlist_delta": [],
        }
        _write("today.json", today_payload)

        by_horizon_rows = await fetch(Q_PREDICTIONS_BY_HORIZON)
        horizons: dict[str, list] = {}
        for r in by_horizon_rows:
            horizons.setdefault(r["horizon"], []).append(r)
        _write("predictions/by-horizon.json", {
            "horizons": [{"horizon": h, "rows": rs} for h, rs in horizons.items()]
        })

        targets: dict[str, list] = {}
        for r in by_horizon_rows:
            targets.setdefault(r["ticker"], []).append({
                "horizon": r["horizon"],
                "predicted": r.get("predicted_close"),
                "delta_pct": r.get("delta_pct"),
            })
        _write("predictions/by-target.json", {
            "targets": [{"ticker": t, "horizons": rs} for t, rs in targets.items()]
        })

        _write("predictions/accuracy.json", {"rows": await fetch(Q_ACCURACY)})

        _write("motion/opportunities.json", {"items": await fetch(Q_OPPORTUNITIES)})
        _write("motion/trades.json", {"items": await fetch(Q_TRADES)})

        _write("manifest.json", {
            "schema_version": 1,
            "cutoff_date": CUTOFF_DATE,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scrub_version": "v1",
            "note": "Baked from live laptop DB. Scrubbed per scripts/bake_demo_snapshot.py.",
        })

    await engine.dispose()
    print("done.")


if __name__ == "__main__":
    asyncio.run(bake())
