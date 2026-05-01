"""One-shot: hand-author DSL invalidators for the 6 seeded drafts.

Each draft expressed invalidators as English bullets. We pick the single
most concise + DSL-mappable bullet per draft and persist it as the row's
``invalidator``. Status stays ``active`` — operator may PATCH or refine
further via the route surface.

Run after ``scripts/seed_hypotheses.py``. Idempotent (overwrites whatever
``invalidator`` is currently on each row, including any prior hand-authored
spec).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core import db as _db                           # noqa: E402
from app.hypotheses import service as hyp_service        # noqa: E402
from app.hypotheses import invalidator as inv_dsl        # noqa: E402


# Slug → DSL spec. Picked from the most quantitative bullet in each draft's
# `invalidators:` block. See .claude/hypotheses/draft/*.md for full lists.
PATCHES: dict[str, dict] = {
    "btc-bottom-3m": {
        "op": "series_above_threshold",
        "args": {"symbol": "DX-Y.NYB", "threshold": 110.0, "days_above": 30},
    },
    "btc-rally-24m": {
        "op": "ratio_below_sma",
        "args": {
            "numerator": "BTC-USD",
            "denominator": "GC=F",
            "sma_days": 200,
            "days_below": 90,
        },
    },
    "latam-breakout-18m": {
        "op": "ratio_below_sma",
        "args": {
            "numerator": "ILF",
            "denominator": "SPY",
            "sma_days": 200,
            "days_below": 30,
        },
    },
    "latam-breakout-36m": {
        "op": "ratio_below_sma",
        "args": {
            "numerator": "ILF",
            "denominator": "SPY",
            "sma_days": 200,
            "days_below": 60,
        },
    },
    "saas-mission-critical-2x-18m": {
        "op": "ratio_below_sma",
        "args": {
            "numerator": "IGV",
            "denominator": "SPY",
            "sma_days": 200,
            "days_below": 60,
        },
    },
    "stagflation-regime-24m": {
        "op": "series_above_threshold",
        "args": {"symbol": "DFII10", "threshold": 2.5, "days_above": 90},
    },
}


async def main() -> int:
    # Validate every spec up-front so a typo doesn't half-update.
    for slug, spec in PATCHES.items():
        try:
            inv_dsl.validate_spec(spec)
        except ValueError as e:
            print(f"BAD SPEC for {slug}: {e}")
            return 1

    async with _db.SessionLocal() as session:
        n = 0
        missing: list[str] = []
        for slug, spec in PATCHES.items():
            row = await hyp_service.get_by_slug(session, slug)
            if row is None:
                missing.append(slug)
                continue
            row.invalidator = spec
            n += 1
        await session.commit()

    if missing:
        print(f"missing slugs (run seed first): {missing}")
        return 2
    print(f"patched {n} invalidators")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
