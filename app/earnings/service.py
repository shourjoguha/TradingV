"""Service layer for the earnings calendar.

Public functions:

- ``compute_universe()`` — roster ∪ The Street Tier 1+2 over last 4 snapshots,
  capped at 150 with 90-day TTL on prior appearances.
- ``refresh_for_ticker(ticker)`` — yfinance primary, NASDAQ fallback, EDGAR
  confirms ``confirmed_at``. Idempotent.
- ``refresh_all(force=False)`` — single tick. Tiered cadence:
  weekly full universe + per-ticker on-demand when ``expected_at`` ≤ 14d.
- ``upcoming_earnings(days)`` — list for the Today panel.
- ``in_trigger_window(...)`` — used by the IR channel poller.
- ``purge_stale_universe(ttl_days=90)`` — drops rows whose ``last_universe_at``
  is older than the TTL.
"""
from __future__ import annotations

import datetime
import logging
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core import db as _db
from app.earnings.models import EarningsCalendarRow
from app.watchlist.models import WatchlistEntry


logger = logging.getLogger(__name__)


UNIVERSE_CAP = 150
DEFAULT_TTL_DAYS = 90
TRIGGER_DAYS_BEFORE = 0
TRIGGER_DAYS_AFTER = 3
NY_TZ = ZoneInfo("America/New_York")
STALE_DATE_TOLERANCE_DAYS = 7


# ---------------------------------------------------------------------------
# Universe — roster ∪ The Street tier 1+2 last 4 snapshots, capped 150.
# ---------------------------------------------------------------------------


async def _street_tickers_recent(snapshots: int = 4) -> list[str]:
    """Pull tier-1 + tier-2 tickers from the most recent N Street snapshots.

    Reads via ``tools.the_street.query`` so we share the same TSV-parsing
    code path as the CLI. Best-effort: if the helper isn't importable, we
    return an empty list and the universe falls back to roster only.
    """
    try:
        from tools.the_street import query as _street_q
    except Exception:  # noqa: BLE001
        return []

    try:
        snaps = _street_q.list_snapshots()[:snapshots]
    except Exception as e:  # noqa: BLE001
        logger.warning("street snapshots unavailable: %s", e)
        return []

    tickers: set[str] = set()
    for snap in snaps:
        for tier in (1, 2):
            try:
                rows = _street_q.list_tier(tier, snapshot=snap)
            except Exception:  # noqa: BLE001
                continue
            for row in rows or []:
                t = (row.get("ticker") or row.get("symbol") or "").strip().upper()
                if t:
                    tickers.add(t)
    return sorted(tickers)


async def _roster_tickers() -> list[str]:
    async with _db.SessionLocal() as session:
        rows = await session.execute(
            select(WatchlistEntry.symbol).order_by(WatchlistEntry.symbol)
        )
        return [r[0] for r in rows]


async def compute_universe() -> list[str]:
    """Return the rolling earnings universe (roster ∪ Street tier1+2),
    capped at ``UNIVERSE_CAP``. Order: roster first, then street.

    The cap protects against pathological growth if Street tiers explode.
    """
    roster = await _roster_tickers()
    street = await _street_tickers_recent(snapshots=4)
    seen: set[str] = set()
    out: list[str] = []
    for t in list(roster) + list(street):
        u = t.upper()
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= UNIVERSE_CAP:
            break
    return out


# ---------------------------------------------------------------------------
# Provider chain — yfinance → NASDAQ → EDGAR confirm.
# ---------------------------------------------------------------------------


def _is_stale(d: Optional[datetime.date], today: datetime.date) -> bool:
    if d is None:
        return True
    return d < today - datetime.timedelta(days=STALE_DATE_TOLERANCE_DAYS)


def _yfinance_next_earnings(ticker: str) -> Optional[datetime.date]:
    """Best-effort yfinance lookup. Returns None on any failure.

    yfinance returns either a Timestamp or a list; we collapse both.
    """
    try:
        import yfinance as yf
    except Exception:  # noqa: BLE001
        return None
    try:
        t = yf.Ticker(ticker)
        cal = getattr(t, "calendar", None)
        if cal is None:
            return None
        # yfinance has shifted shapes across releases. Handle dict + DF.
        if hasattr(cal, "to_dict"):
            cal = cal.to_dict()
        if isinstance(cal, dict):
            for key in ("Earnings Date", "earningsDate", "earnings_date"):
                if key in cal and cal[key]:
                    candidate = cal[key]
                    if isinstance(candidate, (list, tuple)):
                        candidate = candidate[0]
                    if hasattr(candidate, "date"):
                        return candidate.date()
                    if isinstance(candidate, datetime.datetime):
                        return candidate.date()
                    if isinstance(candidate, datetime.date):
                        return candidate
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug("yfinance(%s) failed: %s", ticker, e)
        return None


def _nasdaq_next_earnings(ticker: str) -> Optional[datetime.date]:
    """Free NASDAQ JSON. Returns None when unreachable.

    Best-effort fallback when yfinance returns nothing (or stale).
    """
    try:
        import urllib.request
        import json

        url = (
            f"https://api.nasdaq.com/api/calendar/earnings?date="
            f"{datetime.date.today().isoformat()}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; trader-app/1.0)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        rows = (data or {}).get("data", {}).get("rows") or []
        for row in rows:
            sym = (row.get("symbol") or "").upper()
            if sym == ticker.upper():
                # NASDAQ returns ISO date strings in the "date" column.
                d = row.get("date")
                if d:
                    try:
                        return datetime.date.fromisoformat(str(d).split("T")[0])
                    except ValueError:
                        return None
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug("nasdaq(%s) failed: %s", ticker, e)
        return None


def _edgar_confirm_8k_item_202(ticker: str) -> Optional[datetime.date]:
    """Look for an 8-K filing tagged Item 2.02 within the last 5 days.

    Best-effort. ``ingest_edgar`` already does the CIK lookup + Atom fetch;
    we reuse those primitives. Non-US tickers (no CIK) return None.
    """
    try:
        from tools.vault_indexer.ingest import ingest_edgar as _edgar
    except Exception:  # noqa: BLE001
        return None
    try:
        cik = _edgar.resolve_cik(ticker)
    except Exception:  # noqa: BLE001
        return None
    if not cik:
        return None
    try:
        entries = _edgar.parse_atom(cik=cik, form_types=["8-K"], max_per_form=5)
    except Exception:  # noqa: BLE001
        return None
    today = datetime.date.today()
    for entry in entries or []:
        # Only keep recent + Item 2.02 hints in the title/summary.
        filed_at = entry.get("filed_at") or entry.get("updated")
        if not filed_at:
            continue
        try:
            filed_date = datetime.datetime.fromisoformat(
                str(filed_at).replace("Z", "+00:00")
            ).date()
        except ValueError:
            continue
        if (today - filed_date).days > 5:
            continue
        title = str(entry.get("title") or "").lower()
        summary = str(entry.get("summary") or "").lower()
        if "2.02" in title or "2.02" in summary or "results of operations" in summary:
            return filed_date
    return None


# ---------------------------------------------------------------------------
# Refresh primitives.
# ---------------------------------------------------------------------------


async def refresh_for_ticker(ticker: str) -> dict:
    """Refresh a single ticker's row. Idempotent. Never raises."""
    today = datetime.date.today()
    expected: Optional[datetime.date] = _yfinance_next_earnings(ticker)
    source = "yfinance"
    if _is_stale(expected, today):
        expected = _nasdaq_next_earnings(ticker)
        source = "nasdaq"
    if _is_stale(expected, today):
        expected = None
        source = "miss"

    confirmed = _edgar_confirm_8k_item_202(ticker)

    now = datetime.datetime.now(datetime.timezone.utc)
    async with _db.SessionLocal() as session:
        row = await session.get(EarningsCalendarRow, ticker)
        if row is None:
            row = EarningsCalendarRow(
                ticker=ticker,
                expected_at=expected,
                confirmed_at=confirmed,
                source=source,
                fetched_at=now,
                last_error=None if expected else "no_provider_returned_date",
                first_seen_at=now,
                last_universe_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.expected_at = expected
            row.confirmed_at = confirmed or row.confirmed_at
            row.source = source
            row.fetched_at = now
            row.last_error = None if expected else "no_provider_returned_date"
            row.last_universe_at = now
            row.updated_at = now
        await session.commit()
    return {
        "ticker": ticker,
        "expected_at": expected.isoformat() if expected else None,
        "source": source,
        "confirmed_at": confirmed.isoformat() if confirmed else None,
    }


async def refresh_all(force: bool = False) -> dict:
    """One tick of the earnings calendar refresh.

    Tiered cadence:
      • weekly full universe refresh
      • per-ticker on-demand when ``expected_at`` ≤ 14 days
      • skip if ``fetched_at`` within last 7 days (unless force)
    """
    universe = await compute_universe()
    today = datetime.date.today()
    one_week_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)

    counts = {"refreshed": 0, "skipped": 0, "errors": 0}
    async with _db.SessionLocal() as session:
        existing_rows = (
            await session.execute(select(EarningsCalendarRow))
        ).scalars().all()
        existing = {r.ticker: r for r in existing_rows}

    for ticker in universe:
        row = existing.get(ticker)
        if not force and row is not None and row.fetched_at is not None:
            close_to_release = (
                row.expected_at is not None
                and (row.expected_at - today).days <= 14
            )
            recently_fetched = row.fetched_at >= one_week_ago
            if recently_fetched and not close_to_release:
                # Bump last_universe_at so the TTL purge doesn't drop us.
                row.last_universe_at = datetime.datetime.now(datetime.timezone.utc)
                async with _db.SessionLocal() as s2:
                    obj = await s2.get(EarningsCalendarRow, ticker)
                    if obj is not None:
                        obj.last_universe_at = row.last_universe_at
                        obj.updated_at = row.last_universe_at
                        await s2.commit()
                counts["skipped"] += 1
                continue
        try:
            await refresh_for_ticker(ticker)
            counts["refreshed"] += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("refresh_for_ticker(%s) failed: %s", ticker, e)
            counts["errors"] += 1
    return counts


async def purge_stale_universe(ttl_days: int = DEFAULT_TTL_DAYS) -> int:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=ttl_days
    )
    async with _db.SessionLocal() as session:
        rows = (
            await session.execute(
                select(EarningsCalendarRow).where(
                    EarningsCalendarRow.last_universe_at < cutoff
                )
            )
        ).scalars().all()
        for row in rows:
            await session.delete(row)
        await session.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# Read API.
# ---------------------------------------------------------------------------


async def upcoming_earnings(
    days: int = 30,
) -> list[dict]:
    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=days)
    async with _db.SessionLocal() as session:
        rows = (
            await session.execute(
                select(EarningsCalendarRow)
                .where(EarningsCalendarRow.expected_at.is_not(None))
                .where(EarningsCalendarRow.expected_at >= today)
                .where(EarningsCalendarRow.expected_at <= horizon)
                .order_by(EarningsCalendarRow.expected_at)
            )
        ).scalars().all()
    return [
        {
            "ticker": r.ticker,
            "expected_at": r.expected_at.isoformat() if r.expected_at else None,
            "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
            "source": r.source,
        }
        for r in rows
    ]


async def get_for_ticker(ticker: str) -> Optional[dict]:
    async with _db.SessionLocal() as session:
        row = await session.get(EarningsCalendarRow, ticker.upper())
    if row is None:
        return None
    return {
        "ticker": row.ticker,
        "expected_at": row.expected_at.isoformat() if row.expected_at else None,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "source": row.source,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        "last_error": row.last_error,
    }


# ---------------------------------------------------------------------------
# Trigger-window check (sync — used by youtube_channel.is_due()).
# ---------------------------------------------------------------------------


def in_trigger_window(
    *,
    expected_at: Optional[datetime.date],
    days_before: int = TRIGGER_DAYS_BEFORE,
    days_after: int = TRIGGER_DAYS_AFTER,
    now: Optional[datetime.datetime] = None,
) -> bool:
    """Returns True if today (NY tz) is within
    [expected - days_before, expected + days_after]."""
    if expected_at is None:
        return False
    now = now or datetime.datetime.now(NY_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=NY_TZ)
    today_ny = now.astimezone(NY_TZ).date()
    start = expected_at - datetime.timedelta(days=days_before)
    end = expected_at + datetime.timedelta(days=days_after)
    return start <= today_ny <= end


def channel_in_trigger_window(
    *,
    earnings_trigger: dict,
    earnings_dates: dict[str, Optional[datetime.date]],
    now: Optional[datetime.datetime] = None,
) -> bool:
    """A multi-ticker channel fires if ANY ticker is in its window.

    ``earnings_trigger`` shape::

        earnings_trigger:
          tickers: [GOOGL, GOOG]
          days_before: 0
          days_after: 3
    """
    if not earnings_trigger:
        return False
    tickers = list(earnings_trigger.get("tickers") or [])
    if not tickers:
        return False
    days_before = int(earnings_trigger.get("days_before", TRIGGER_DAYS_BEFORE))
    days_after = int(earnings_trigger.get("days_after", TRIGGER_DAYS_AFTER))
    for t in tickers:
        d = earnings_dates.get(t.upper())
        if in_trigger_window(
            expected_at=d, days_before=days_before, days_after=days_after, now=now
        ):
            return True
    return False
