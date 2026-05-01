"""Seed the ``hypothesis`` table from drafts in ``.claude/hypotheses/draft/``.

Idempotent on ``slug``. Run twice → no-op the second pass unless
``--rewrite`` is passed (then non-DSL fields are refreshed; the
``invalidator`` column is **never** overwritten because the operator
hand-authors that DSL after seeding).

The drafts use a few claim_type values that don't match our enum
(``absolute``, ``regime_shift``); we normalise at seed time.

Usage:
    python scripts/seed_hypotheses.py [--rewrite]
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core import db as _db                                 # noqa: E402
from app.hypotheses.models import (                            # noqa: E402
    ALL_CLAIM_TYPES,
    CLAIM_REGIME,
    CLAIM_SINGLE_NAME,
    CLAIM_TACTICAL,
    Hypothesis,
)
from app.hypotheses import service as hyp_service              # noqa: E402

logger = logging.getLogger("seed-hypotheses")
DRAFT_DIR = REPO_ROOT / ".claude" / "hypotheses" / "draft"


# Map draft-frontmatter claim values to our enum.
CLAIM_NORMALIZE = {
    "absolute": CLAIM_SINGLE_NAME,
    "regime_shift": CLAIM_REGIME,
    "regime": CLAIM_REGIME,
    "tactical": CLAIM_TACTICAL,
    "breakout": "breakout",
    "single_name": CLAIM_SINGLE_NAME,
}


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    return yaml.safe_load(parts[1]) or {}, parts[2].strip()


def _draft_to_payload(fm: dict, body: str) -> dict[str, Any]:
    raw_claim = (fm.get("claim_type") or "regime").strip().lower()
    claim_type = CLAIM_NORMALIZE.get(raw_claim, CLAIM_REGIME)
    if claim_type not in ALL_CLAIM_TYPES:
        raise ValueError(f"unknown claim_type: {raw_claim}")
    return {
        "slug": fm["slug"],
        "title": fm.get("name") or fm["slug"],
        "claim_type": claim_type,
        "axis": (fm.get("axis") or "uncategorized").strip(),
        "parent_id_slug": fm.get("parent_id"),         # resolved in pass 2
        "precondition_id_slug": fm.get("precondition_id"),
        "primary_metric": fm.get("primary_metric") or fm["slug"],
        "tracking_signal": fm.get("tracking_signal") or fm.get("primary_metric") or fm["slug"],
        # Ingestion seeds with a manual placeholder. Operator hand-edits
        # via PATCH /v1/hypotheses/{id} after seeding to express the
        # invalidators in the DSL.
        "invalidator": {"op": "manual", "args": {}},
        "ttl_months": int(fm.get("ttl_months") or 12),
        "body_md": body,
    }


async def main(rewrite: bool) -> int:
    if not DRAFT_DIR.is_dir():
        logger.error("draft dir not found: %s", DRAFT_DIR)
        return 1
    drafts = [p for p in sorted(DRAFT_DIR.glob("*.md")) if p.name != "template.md"]
    if not drafts:
        logger.warning("no drafts to seed in %s", DRAFT_DIR)
        return 0

    logger.info("seeding %d drafts from %s", len(drafts), DRAFT_DIR)

    payloads: list[dict[str, Any]] = []
    for path in drafts:
        try:
            fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
            payloads.append(_draft_to_payload(fm, body))
        except Exception as e:  # noqa: BLE001
            logger.error("failed to parse %s: %s", path.name, e)
            return 2

    inserted, updated, skipped = 0, 0, 0
    async with _db.SessionLocal() as session:
        existing_by_slug: dict[str, Hypothesis] = {}
        # Pass 1: insert/update without parent/precondition FKs.
        for p in payloads:
            existing = await hyp_service.get_by_slug(session, p["slug"])
            if existing is None:
                created = datetime.datetime.now(tz=datetime.timezone.utc)
                row = Hypothesis(
                    slug=p["slug"],
                    title=p["title"],
                    claim_type=p["claim_type"],
                    axis=p["axis"],
                    primary_metric=p["primary_metric"],
                    tracking_signal=p["tracking_signal"],
                    invalidator=p["invalidator"],
                    ttl_months=p["ttl_months"],
                    created_at=created,
                    expires_at=created + datetime.timedelta(days=p["ttl_months"] * 30),
                    body_md=p["body_md"],
                )
                session.add(row)
                inserted += 1
                existing_by_slug[p["slug"]] = row
            elif rewrite:
                existing.title = p["title"]
                existing.axis = p["axis"]
                existing.primary_metric = p["primary_metric"]
                existing.tracking_signal = p["tracking_signal"]
                existing.body_md = p["body_md"]
                # NOT touching invalidator or status — operator authority.
                updated += 1
                existing_by_slug[p["slug"]] = existing
            else:
                skipped += 1
                existing_by_slug[p["slug"]] = existing
        await session.flush()

        # Pass 2: resolve parent_id_slug + precondition_id_slug → UUIDs.
        for p in payloads:
            row = existing_by_slug.get(p["slug"])
            if row is None:
                continue
            for slug_field, fk_field in (
                ("parent_id_slug", "parent_id"),
                ("precondition_id_slug", "precondition_id"),
            ):
                slug = p.get(slug_field)
                if slug:
                    parent = existing_by_slug.get(slug)
                    if parent:
                        setattr(row, fk_field, parent.id)
                    else:
                        logger.warning(
                            "%s references unknown %s=%s — leaving null",
                            p["slug"], slug_field, slug,
                        )

        await session.commit()

    logger.warning(
        "DSL invalidators seeded as 'manual'. Hand-author via PATCH /v1/hypotheses/{id} "
        "to make them auto-evaluable."
    )
    print(f"seed complete: inserted={inserted}, updated={updated}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--rewrite", action="store_true", help="Update title/body on existing rows.")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(rewrite=args.rewrite)))
