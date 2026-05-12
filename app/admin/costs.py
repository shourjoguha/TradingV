"""Anthropic spend aggregator — Phase 5 cost dashboard.

Sums est_cost_usd across:
  - research_queries (Sonnet — Research stress-tests)
  - tv_context_items (Sonnet — vision summaries on screenshot ingest)

5-minute in-process cache so the Costs tab doesn't hammer the DB on every
auto-refresh; recent activity still shows within minutes.
"""
from __future__ import annotations

import datetime
import time
from collections import defaultdict
from typing import Optional

from sqlalchemy import select

from app.core import db as _db
from app.research.models import ResearchQuery
from app.tv_context.models import TVContextItem


CACHE_TTL_SECONDS = 300

_cache: dict[tuple, tuple[float, dict]] = {}


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _month_bounds(month: Optional[str]) -> tuple[datetime.datetime, datetime.datetime]:
    if month:
        year, mon = (int(p) for p in month.split("-"))
        start = datetime.datetime(year, mon, 1, tzinfo=datetime.timezone.utc)
    else:
        now = _utc_now()
        start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


async def monthly_breakdown(month: Optional[str] = None) -> dict:
    """Return totals + counts for the given month (YYYY-MM, default current)."""
    cache_key = ("monthly", month or "current")
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    start, end = _month_bounds(month)
    research_total = 0.0
    research_count = 0
    vision_total = 0.0
    vision_count = 0

    async with _db.SessionLocal() as session:
        rq_rows = (
            await session.execute(
                select(ResearchQuery.est_cost_usd, ResearchQuery.id).where(
                    ResearchQuery.asked_at >= start,
                    ResearchQuery.asked_at < end,
                )
            )
        ).all()
        for cost, _id in rq_rows:
            if cost is not None:
                try:
                    research_total += float(cost)
                except (TypeError, ValueError):
                    pass
            research_count += 1

        tv_rows = (
            await session.execute(
                select(TVContextItem.payload).where(
                    TVContextItem.captured_at >= start,
                    TVContextItem.captured_at < end,
                    TVContextItem.kind == "screenshot",
                )
            )
        ).scalars().all()
        for payload in tv_rows:
            if not isinstance(payload, dict):
                continue
            vision = payload.get("vision") if isinstance(payload, dict) else None
            if not isinstance(vision, dict):
                continue
            cost = vision.get("cost_usd")
            if cost is not None:
                try:
                    vision_total += float(cost)
                except (TypeError, ValueError):
                    pass
                vision_count += 1

    result = {
        "month": (month or _utc_now().strftime("%Y-%m")),
        "research_total_usd": round(research_total, 4),
        "research_count": research_count,
        "vision_total_usd": round(vision_total, 4),
        "vision_count": vision_count,
        "total_usd": round(research_total + vision_total, 4),
    }
    _cache[cache_key] = (time.monotonic(), result)
    return result


async def daily_series(days: int = 30) -> list[dict]:
    """Return per-day totals for the last N days. Used by the stacked-area chart."""
    cache_key = ("daily", days)
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    end = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - datetime.timedelta(days=days)

    by_day_research: dict[str, float] = defaultdict(float)
    by_day_vision: dict[str, float] = defaultdict(float)

    async with _db.SessionLocal() as session:
        rq_rows = (
            await session.execute(
                select(ResearchQuery.asked_at, ResearchQuery.est_cost_usd).where(
                    ResearchQuery.asked_at >= start,
                )
            )
        ).all()
        for asked, cost in rq_rows:
            if cost is None:
                continue
            day = asked.date().isoformat()
            try:
                by_day_research[day] += float(cost)
            except (TypeError, ValueError):
                pass

        tv_rows = (
            await session.execute(
                select(TVContextItem.captured_at, TVContextItem.payload).where(
                    TVContextItem.captured_at >= start,
                    TVContextItem.kind == "screenshot",
                )
            )
        ).all()
        for captured, payload in tv_rows:
            if not isinstance(payload, dict):
                continue
            vision = payload.get("vision")
            if not isinstance(vision, dict):
                continue
            cost = vision.get("cost_usd")
            if cost is None:
                continue
            day = captured.date().isoformat()
            try:
                by_day_vision[day] += float(cost)
            except (TypeError, ValueError):
                pass

    series: list[dict] = []
    cur = start
    while cur < end:
        d = cur.date().isoformat()
        series.append(
            {
                "date": d,
                "research_usd": round(by_day_research.get(d, 0.0), 4),
                "vision_usd": round(by_day_vision.get(d, 0.0), 4),
            }
        )
        cur += datetime.timedelta(days=1)

    _cache[cache_key] = (time.monotonic(), series)
    return series


async def top_queries_by_cost(limit: int = 10) -> list[dict]:
    """Most expensive research queries this month — drill-down list."""
    start, end = _month_bounds(None)
    async with _db.SessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    ResearchQuery.id,
                    ResearchQuery.query,
                    ResearchQuery.est_cost_usd,
                    ResearchQuery.asked_at,
                ).where(
                    ResearchQuery.asked_at >= start,
                    ResearchQuery.asked_at < end,
                )
                .order_by(ResearchQuery.est_cost_usd.desc().nulls_last())
                .limit(limit)
            )
        ).all()
    return [
        {
            "id": row[0],
            "query": (row[1] or "")[:160],
            "est_cost_usd": float(row[2]) if row[2] is not None else 0.0,
            "asked_at": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    ]


def clear_cache() -> None:
    _cache.clear()
