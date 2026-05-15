"""Ticker review queue service — Phase D.

Public surface:

* ``enqueue_or_bump(ticker, video_id, channel, snippet)`` — upsert a row,
  bumping ``times_seen`` + appending channel/video/snippet (capped at 3 each).
  Resurrects dismissed rows past the 90d re-eligibility window.
* ``list_pending(limit=10)`` — Today strip query. Filters
  ``times_seen >= MIN_SEEN`` (anti-noise) and ``status='pending'``.
* ``list_all(...)`` — full review (admin / historical).
* ``resolve(entry_id, action, board_id=None)`` — atomic chain to watchlist
  or boards service, then status update.
* ``weekly_digest_md()`` — markdown rendering for the Sunday vault digest.
* ``enqueue_or_bump_sync`` — thin sync wrapper for the indexer (which runs
  off the event loop). Best-effort: swallow exceptions, log.

Re-eligibility: ``_RE_ELIGIBILITY_DAYS = 90``. Dismissed rows can
re-surface IFF (now - resolved_at) > 90d AND a new mention arrives.
The previous resolved_at is stashed in ``previously_dismissed_at`` so
the Today strip can render the chip.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from typing import Any, Iterable, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError

from app.core import db as _db
from app.ticker_review.models import TickerReviewEntry

logger = logging.getLogger(__name__)


# ---- Tunables ---------------------------------------------------------------

_RE_ELIGIBILITY_DAYS = 90
"""Dismissed rows resurface only after this many days IF re-encountered."""

MIN_SEEN = 2
"""Today strip surfaces entries seen >= MIN_SEEN times (anti-noise filter)."""

_SNIPPET_CAP = 3
"""Keep last N snippets / channels / video_ids per entry."""


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _ensure_aware(value: Optional[_dt.datetime]) -> Optional[_dt.datetime]:
    """Coerce a possibly-naive db datetime to UTC-aware. SQLite stores
    timestamps without tz; Postgres preserves it. Either way, normalize."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


def _append_capped(existing: Optional[list], value: str, cap: int = _SNIPPET_CAP) -> list:
    """Append ``value`` to ``existing`` if absent; truncate to last ``cap`` items.

    Order = most-recent last. Dedupes case-sensitively.
    """
    out = list(existing or [])
    if value and value not in out:
        out.append(value)
    if len(out) > cap:
        out = out[-cap:]
    return out


# ---- Mutations --------------------------------------------------------------

async def enqueue_or_bump(
    *,
    ticker: str,
    video_id: str,
    channel: str,
    snippet: str,
) -> Optional[TickerReviewEntry]:
    """Upsert a queue row. Returns the persisted entry, or None when the
    ticker is empty / clearly invalid."""
    sym = _normalize_ticker(ticker)
    if not sym or len(sym) > 50:
        return None
    snippet = (snippet or "").strip()[:280]
    channel = (channel or "").strip()[:80] or "unknown"
    video_id = (video_id or "").strip()[:80]

    now = _utcnow()
    async with _db.SessionLocal() as session:
        row = await session.scalar(
            select(TickerReviewEntry).where(TickerReviewEntry.ticker == sym)
        )
        if row is None:
            row = TickerReviewEntry(
                ticker=sym,
                first_seen_at=now,
                last_seen_at=now,
                times_seen=1,
                channels=[channel] if channel else [],
                recent_video_ids=[video_id] if video_id else [],
                recent_caption_snippets=[snippet] if snippet else [],
                status="pending",
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                # Concurrent insert lost the race; reload + bump.
                await session.rollback()
                row = await session.scalar(
                    select(TickerReviewEntry).where(TickerReviewEntry.ticker == sym)
                )
                if row is None:
                    return None
            else:
                await session.refresh(row)
                return row

        # Existing row — bump.
        previously_dismissed = None
        if row.status == "dismissed":
            resolved_at_aware = _ensure_aware(row.resolved_at) or now
            age = now - resolved_at_aware
            if age.days >= _RE_ELIGIBILITY_DAYS:
                # Resurrect: stash old resolved_at so UI can show the chip.
                previously_dismissed = row.resolved_at
                row.status = "pending"
                row.resolved_at = None
                row.resolved_target = None
            else:
                # Inside the suppression window — record but don't resurface.
                row.times_seen = (row.times_seen or 0) + 1
                row.last_seen_at = now
                row.channels = _append_capped(row.channels, channel)
                row.recent_video_ids = _append_capped(row.recent_video_ids, video_id)
                row.recent_caption_snippets = _append_capped(
                    row.recent_caption_snippets, snippet
                )
                await session.commit()
                await session.refresh(row)
                return row

        row.times_seen = (row.times_seen or 0) + 1
        row.last_seen_at = now
        row.channels = _append_capped(row.channels, channel)
        row.recent_video_ids = _append_capped(row.recent_video_ids, video_id)
        row.recent_caption_snippets = _append_capped(
            row.recent_caption_snippets, snippet
        )
        if previously_dismissed is not None:
            row.previously_dismissed_at = previously_dismissed
        await session.commit()
        await session.refresh(row)
        return row


def enqueue_or_bump_sync(
    *,
    ticker: str,
    video_id: str,
    channel: str,
    snippet: str,
) -> None:
    """Sync wrapper for callers off the event loop (indexer). Best-effort.

    Logs + swallows on failure so a queue write never blocks ingest.
    """
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        coro = enqueue_or_bump(
            ticker=ticker, video_id=video_id, channel=channel, snippet=snippet
        )
        if loop and loop.is_running():
            # Schedule on the existing loop; fire-and-forget. We are already
            # inside an async context (rare for the indexer but possible).
            asyncio.ensure_future(coro)
        else:
            asyncio.run(coro)
    except Exception as e:  # noqa: BLE001
        logger.warning("ticker-review enqueue failed for %s: %s", ticker, e)


# ---- Reads ------------------------------------------------------------------

async def list_pending(
    *, limit: int = 10, min_seen: int = MIN_SEEN
) -> List[TickerReviewEntry]:
    async with _db.SessionLocal() as session:
        rows = await session.execute(
            select(TickerReviewEntry)
            .where(TickerReviewEntry.status == "pending")
            .where(TickerReviewEntry.times_seen >= min_seen)
            .order_by(desc(TickerReviewEntry.last_seen_at))
            .limit(limit)
        )
        return list(rows.scalars().all())


async def list_all(
    *,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[TickerReviewEntry]:
    async with _db.SessionLocal() as session:
        q = select(TickerReviewEntry)
        if status:
            q = q.where(TickerReviewEntry.status == status)
        q = q.order_by(desc(TickerReviewEntry.last_seen_at)).limit(limit)
        rows = await session.execute(q)
        return list(rows.scalars().all())


async def get_entry(entry_id: int) -> Optional[TickerReviewEntry]:
    async with _db.SessionLocal() as session:
        return await session.get(TickerReviewEntry, entry_id)


async def pending_count() -> int:
    async with _db.SessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(TickerReviewEntry)
                .where(TickerReviewEntry.status == "pending")
                .where(TickerReviewEntry.times_seen >= MIN_SEEN)
            )
            or 0
        )


# ---- Resolution -------------------------------------------------------------

async def resolve(
    entry_id: int,
    *,
    action: str,
    board_id: Optional[str] = None,
) -> TickerReviewEntry:
    """Apply an operator decision. Chains atomically to the destination
    surface (roster / board); on chain failure the queue row remains
    pending and the exception bubbles up to the route.
    """
    if action not in {"add_to_roster", "add_to_board", "dismiss"}:
        raise ValueError(f"unknown action: {action}")
    if action == "add_to_board" and not board_id:
        raise ValueError("board_id required for add_to_board")

    entry = await get_entry(entry_id)
    if entry is None:
        raise LookupError(f"ticker_review entry {entry_id} not found")

    sym = entry.ticker

    if action == "add_to_roster":
        from app.watchlist import service as _wl

        await _wl.add_entry(sym)
        target = None
    elif action == "add_to_board":
        from app.boards import service as _boards

        try:
            await _boards.add_ticker(board_id, ticker=sym)
        except LookupError:
            raise
        target = board_id
    else:
        target = None  # dismiss

    now = _utcnow()
    async with _db.SessionLocal() as session:
        row = await session.get(TickerReviewEntry, entry_id)
        if row is None:
            raise LookupError(f"ticker_review entry {entry_id} not found")
        row.status = {
            "add_to_roster": "added_to_roster",
            "add_to_board": "added_to_board",
            "dismiss": "dismissed",
        }[action]
        row.resolved_at = now
        row.resolved_target = target
        await session.commit()
        await session.refresh(row)
        return row


# ---- Weekly digest ----------------------------------------------------------

_DIGEST_START = "<!-- ticker-review-queue:auto-start -->"
_DIGEST_END = "<!-- ticker-review-queue:auto-end -->"


async def weekly_digest_md() -> str:
    """Render the Sunday vault digest. Plain markdown — sentinel-wrapped
    so operator notes around the block survive regeneration."""
    pending = await list_all(status="pending", limit=500)
    now_iso = _utcnow().strftime("%Y-%m-%d")
    lines: List[str] = [
        _DIGEST_START,
        "",
        f"# Ticker Review Queue ({now_iso})",
        "",
        "Tickers identified by video-vision Stage 1 that are not yet in the operator's",
        "roster / boards / The Street. Resolve via the Today strip or open the entry to",
        "add to a watchlist.",
        "",
    ]
    if not pending:
        lines += ["_No pending tickers._", "", _DIGEST_END]
        return "\n".join(lines)

    surface = [e for e in pending if (e.times_seen or 0) >= MIN_SEEN]
    suppressed = [e for e in pending if (e.times_seen or 0) < MIN_SEEN]

    if surface:
        lines.append(f"## Surfaced ({len(surface)})")
        lines.append("")
        for e in surface:
            channels = ", ".join(e.channels or []) or "—"
            snippet = (e.recent_caption_snippets or [""])[-1] or "—"
            chip = ""
            if e.previously_dismissed_at:
                chip = (
                    f" _(previously dismissed "
                    f"{e.previously_dismissed_at.strftime('%Y-%m-%d')})_"
                )
            lines.append(
                f"- **{e.ticker}** — seen {e.times_seen}× across {channels}{chip}"
            )
            lines.append(f"  > {snippet}")
        lines.append("")

    if suppressed:
        lines.append(
            f"## Below surface threshold ({len(suppressed)} — seen once each)"
        )
        lines.append("")
        for e in suppressed:
            channels = ", ".join(e.channels or []) or "—"
            lines.append(f"- {e.ticker} (in {channels})")
        lines.append("")

    lines.append(_DIGEST_END)
    return "\n".join(lines)


async def write_weekly_digest(vault_path: str) -> Optional[str]:
    """Write the digest to ``<vault_path>/Topics/_ticker-review-queue.md``.

    Returns the absolute path on success, None when no vault configured.
    Sentinel-bounded so operator notes outside the block survive.
    """
    from pathlib import Path

    if not vault_path:
        return None
    root = Path(vault_path).expanduser()
    if not root.exists():
        logger.warning("ticker-review digest: vault path %s missing", root)
        return None
    target = root / "Topics" / "_ticker-review-queue.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    new_block = await weekly_digest_md()

    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if _DIGEST_START in existing and _DIGEST_END in existing:
            head, _, rest = existing.partition(_DIGEST_START)
            _, _, tail = rest.partition(_DIGEST_END)
            merged = head + new_block + tail
        else:
            merged = existing.rstrip() + "\n\n" + new_block + "\n"
    else:
        merged = new_block + "\n"

    target.write_text(merged, encoding="utf-8")
    return str(target)
