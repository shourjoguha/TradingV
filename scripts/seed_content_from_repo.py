"""Seed the ``content`` hierarchy with the Trade/Off Season 1 backlog.

Operationalizes the curriculum in
``.claude/plans/video-series-platform-design.md`` §8 — one episode per real
shipped artifact (ADR / roadmap retro). Every episode carries a
``source_ref`` so the verifiability invariant holds.

Idempotent on slug at every level (re-run = no-op for existing rows).
New episodes are created in ``status='idea'``.

Usage:
    python scripts/seed_content_from_repo.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from app.content import service  # noqa: E402
from app.content.models import (  # noqa: E402
    ContentArc,
    ContentDomain,
    ContentEpisode,
    ContentSeries,
)
from app.core import db as _db  # noqa: E402


DOMAIN = {"slug": "trading", "title": "Trading"}
SERIES = {
    "slug": "trade-off",
    "title": "Trade/Off",
    "promise": "Every episode is one real decision we shipped — told with a receipt.",
}

# (arc_slug, arc_title, theme, [(ep_slug, ep_title, hook_pattern, source_ref), ...])
ARCS = [
    (
        "decisions-that-say-no",
        "Decisions that say no",
        "The judgment arc — what we chose NOT to build.",
        [
            ("deleted-rules-engine", "I deleted my trading rules engine", "wrong_turn", "adr:007"),
            ("one-database-no-redis", "One database. No Redis. No regrets (yet)", "refusal", "adr:008"),
            ("no-dark-mode", "My trading app has no dark mode — on purpose", "surprising_constraint", "adr:009"),
            ("one-notification-channel", "One notification channel. That's the whole list", "refusal", "adr:006"),
            ("refused-browser-automation", "I refused to automate the browser", "refusal", "adr:016"),
            ("ditched-no-code", "Why I ditched the no-code builder", "wrong_turn", "adr:001"),
        ],
    ),
    (
        "making-the-machine-see",
        "Making the machine see",
        "The video-vision saga — teaching the tool to read charts.",
        [
            ("ai-watches-youtube", "I built an AI that watches finance YouTube for me", "meta", "retro:2026-05-14-video-vision-l2"),
            ("can-2b-read-a-candle", "Can a 2-billion-parameter model read a candlestick?", "grading", "retro:2026-05-14-l3-qwen2vl"),
            ("unknown-tickers", "Teaching the machine the tickers it's never heard of", "the_receipt", "retro:2026-05-14-ticker-review-queue"),
            ("25s-to-87ms", "25 seconds to 87 milliseconds. One word", "the_receipt", "retro:2026-05-16-vault-phase-e"),
        ],
    ),
    (
        "prediction-to-pnl",
        "From prediction to P&L",
        "The signal layer — predictions, grading, attribution.",
        [
            ("grade-your-predictions", "A prediction is worthless until you grade it", "grading", "module:accuracy"),
            ("bidirectional-sync", "My laptop and the cloud sync both ways, privately", "meta", "adr:002"),
            ("self-ranking-signal", "The signal that ranks itself by how often it's right", "the_receipt", "module:opportunities"),
            ("one-click-to-trade", "From one click to a logged trade with attribution", "meta", "retro:2026-05-16-rx-finance-log-trade"),
        ],
    ),
    (
        "build-discipline",
        "Build discipline",
        "How the sausage stays honest.",
        [
            ("demo-cant-lie", "Why my public demo isn't allowed to lie", "honesty_flex", "retro:2026-05-12-demo-claim-audit"),
            ("five-agents-argue", "I let 5 AI agents argue about my UI", "the_argument", "retro:2026-05-17-ux-rework"),
            ("sqlite-only-deadlock", "The deadlock that only happened in SQLite", "lonely_bug", "retro:2026-05-17-tv-context-phase-1"),
            ("847-tests", "847 tests. Here's the one that earned its keep", "the_receipt", "guide:testing"),
        ],
    ),
]


async def _get_domain(slug: str):
    async with _db.SessionLocal() as s:
        return (await s.execute(select(ContentDomain).where(ContentDomain.slug == slug))).scalar_one_or_none()


async def _get_series(domain_id: int, slug: str):
    async with _db.SessionLocal() as s:
        return (
            await s.execute(
                select(ContentSeries).where(
                    ContentSeries.domain_id == domain_id, ContentSeries.slug == slug
                )
            )
        ).scalar_one_or_none()


async def _get_arc(series_id: int, slug: str):
    async with _db.SessionLocal() as s:
        return (
            await s.execute(
                select(ContentArc).where(
                    ContentArc.series_id == series_id, ContentArc.slug == slug
                )
            )
        ).scalar_one_or_none()


async def _get_episode(arc_id: int, slug: str):
    async with _db.SessionLocal() as s:
        return (
            await s.execute(
                select(ContentEpisode).where(
                    ContentEpisode.arc_id == arc_id, ContentEpisode.slug == slug
                )
            )
        ).scalar_one_or_none()


async def seed() -> None:
    created = {"domains": 0, "series": 0, "arcs": 0, "episodes": 0}

    domain = await _get_domain(DOMAIN["slug"])
    if domain is None:
        domain = await service.create_domain(slug=DOMAIN["slug"], title=DOMAIN["title"])
        created["domains"] += 1

    series = await _get_series(domain.id, SERIES["slug"])
    if series is None:
        series = await service.create_series(
            domain_id=domain.id,
            slug=SERIES["slug"],
            title=SERIES["title"],
            promise=SERIES["promise"],
        )
        created["series"] += 1

    for arc_idx, (arc_slug, arc_title, theme, episodes) in enumerate(ARCS):
        arc = await _get_arc(series.id, arc_slug)
        if arc is None:
            arc = await service.create_arc(
                series_id=series.id,
                slug=arc_slug,
                title=arc_title,
                theme=theme,
                order_idx=arc_idx,
            )
            created["arcs"] += 1

        for ep_idx, (slug, title, hook_pattern, source_ref) in enumerate(episodes):
            existing = await _get_episode(arc.id, slug)
            if existing is not None:
                continue
            await service.create_episode(
                arc_id=arc.id,
                slug=slug,
                title=title,
                hook_pattern=hook_pattern,
                source_ref=source_ref,
                order_idx=ep_idx,
            )
            created["episodes"] += 1

    print(
        f"seed_content: +{created['domains']} domain "
        f"+{created['series']} series +{created['arcs']} arcs "
        f"+{created['episodes']} episodes (idempotent on slug)"
    )


if __name__ == "__main__":
    asyncio.run(seed())
