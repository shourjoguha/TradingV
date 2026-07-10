"""Run the Agents lane (TradingAgents) over a list of tickers and snapshot it.

This is the reusable, operator-facing entry point the lane never had: the
service only exposed ``run_for_ticker`` + the ``/v1/agents/run`` endpoint. Point
it at any symbols (they need NOT be on the watchlist), and it will, per ticker:

  1. run the multi-agent debate → a discrete BUY/SELL/HOLD + rationale
     (``app.agents.service.run_for_ticker``, idempotent per ticker/day);
  2. augment that into a structured 6–12mo downside/upside review
     (``app.agents.review.augment_decision``) and persist it onto the
     decision's ``meta`` (``service.attach_review``);
  3. collect everything into a JSON snapshot for ``agents_report.py``.

Best-effort per ticker: one failure is logged and skipped, the batch continues.

Usage:
    python scripts/agents_review.py MSFT PYPL NFLX NOW GOOGL MSTR \
        [--out reports/agents-review-YYYY-MM-DD.json] [--made-on YYYY-MM-DD] \
        [--no-augment]

Prerequisites for REAL decisions (laptop): install requirements-agents.txt,
set AGENTS_ENABLED=true + ANTHROPIC_API_KEY (+ FINNHUB_API_KEY for the online
data path), and a reachable DATABASE_URL (Postgres OR sqlite+aiosqlite). With
the lane disabled the script refuses to emit stub verdicts unless DEBUG_STUB=1.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.agents import review as agents_review  # noqa: E402
from app.agents import service as agents_service  # noqa: E402
from app.agents.adapter import get_engine  # noqa: E402
from app.core.config import SETTINGS  # noqa: E402

logger = logging.getLogger("agents-review")

ENABLE_HELP = (
    "The agents lane is not wired (active engine is the stub). To produce REAL\n"
    "decisions, on your laptop:\n"
    "  pip install -r requirements.txt -r requirements-agents.txt\n"
    "  export AGENTS_ENABLED=true ANTHROPIC_API_KEY=... FINNHUB_API_KEY=...\n"
    "  export DATABASE_URL=sqlite+aiosqlite:///./dev.db   # or your Postgres URL\n"
    "  alembic upgrade head\n"
    "Or set DEBUG_STUB=1 to exercise the pipeline with deterministic stub data."
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the agents lane over a ticker list.")
    p.add_argument("tickers", nargs="+", help="Ticker symbols, e.g. MSFT GOOGL MSTR")
    p.add_argument("--out", default=None, help="JSON snapshot path (default: reports/agents-review-<date>.json)")
    p.add_argument("--made-on", default=None, help="Decision date YYYY-MM-DD (default: today UTC)")
    p.add_argument("--no-augment", action="store_true", help="Skip the 6-12mo downside/upside augmentation")
    return p.parse_args(argv)


def _preflight() -> None:
    """Refuse to emit meaningless stub verdicts unless explicitly in debug."""
    engine = get_engine()
    if engine.name == "stub" and not SETTINGS.DEBUG_STUB:
        print(ENABLE_HELP, file=sys.stderr)
        raise SystemExit(2)
    if engine.name == "stub":
        logger.warning("DEBUG_STUB active — decisions are synthetic, NOT real analysis.")


async def review_tickers(
    tickers: list[str],
    *,
    made_on: datetime.date | None = None,
    augment: bool = True,
) -> dict:
    """Run + (optionally) augment each ticker. Returns a snapshot dict."""
    made_on = made_on or datetime.datetime.now(datetime.timezone.utc).date()
    results: list[dict] = []
    stats = {"scanned": 0, "ok": 0, "failed": 0}

    for raw in tickers:
        sym = raw.strip().upper()
        if not sym:
            continue
        stats["scanned"] += 1
        try:
            decision = await agents_service.run_for_ticker(sym, made_on=made_on)
            if augment:
                rev = agents_review.augment_decision(decision)
                merged = await agents_service.attach_review(decision["id"], rev)
                decision = {**decision, **merged}
            results.append(decision)
            stats["ok"] += 1
            logger.info("%s → %s (%s)", sym, decision.get("stance"),
                        (decision.get("review") or {}).get("buy_level", "n/a"))
        except Exception as e:  # noqa: BLE001 — one bad ticker shouldn't stop the batch
            logger.warning("review failed for %s: %s", sym, e)
            stats["failed"] += 1
            results.append({"ticker": sym, "error": str(e)})

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "made_on": made_on.isoformat(),
        "engine": get_engine().name,
        "stats": stats,
        "decisions": results,
    }


def _default_out(made_on: datetime.date) -> Path:
    return REPO_ROOT / "reports" / f"agents-review-{made_on.isoformat()}.json"


async def _main_async(args: argparse.Namespace) -> int:
    _preflight()
    made_on = (
        datetime.date.fromisoformat(args.made_on) if args.made_on
        else datetime.datetime.now(datetime.timezone.utc).date()
    )
    snapshot = await review_tickers(
        args.tickers, made_on=made_on, augment=not args.no_augment
    )
    out = Path(args.out) if args.out else _default_out(made_on)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    s = snapshot["stats"]
    logger.info("wrote %s  (scanned=%d ok=%d failed=%d)", out, s["scanned"], s["ok"], s["failed"])
    print(str(out))
    return 0 if s["failed"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return asyncio.run(_main_async(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
