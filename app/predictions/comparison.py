"""Comparison query helpers.

Two read-only endpoints expose the prediction history for a frontend:

- :func:`by_target`  — one (ticker, target_date) → actual + every prediction
                        ever made for that bar, sortable by made_on.
- :func:`by_horizon` — grid view: for a target_date, return predictions made
                        ``horizons`` calendar days before, across N tickers.

Both filter through ``?fields=`` and ``?made_on_dow=`` query params via the
:func:`parse_fields` / :func:`parse_dow_filter` helpers.
"""
from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as _db
from app.market_data.models import OhlcvBar
from app.predictions.models import PredictionPoint
from app.tickers.service import normalize as normalize_symbol

# ----------------------------------------------------------------------
# Field selector
# ----------------------------------------------------------------------

_ALL_FIELDS = ("open", "high", "low", "close", "volume", "amount")
_PRESETS: dict[str, tuple[str, ...]] = {
    "o": ("open",),
    "h": ("high",),
    "l": ("low",),
    "c": ("close",),
    "v": ("volume",),
    "a": ("amount",),
    "ohlc": ("open", "high", "low", "close"),
    "ohlcv": ("open", "high", "low", "close", "volume"),
    "all": _ALL_FIELDS,
}
_DEFAULT_FIELDS = _PRESETS["ohlcv"]


def parse_fields(spec: Optional[str]) -> tuple[str, ...]:
    """Parse the ``?fields=`` query param.

    Accepts a preset key (``o|h|l|c|v|a|ohlc|ohlcv|all``) OR a CSV of bare
    field names. Unknown fields are dropped. Empty result falls back to
    the default (OHLCV).
    """
    if not spec:
        return _DEFAULT_FIELDS
    spec = spec.strip().lower()
    if spec in _PRESETS:
        return _PRESETS[spec]
    parts = [p.strip().lower() for p in spec.split(",") if p.strip()]
    valid = tuple(p for p in parts if p in _ALL_FIELDS)
    return valid or _DEFAULT_FIELDS


def parse_dow_filter(spec: Optional[str]) -> Optional[tuple[int, ...]]:
    """Parse ``?made_on_dow=4`` or ``?made_on_dow=0,4`` (Mon=0..Sun=6).

    Returns None if not specified (don't filter), tuple of ints otherwise.
    Out-of-range values are dropped.
    """
    if not spec:
        return None
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            v = int(part)
        except ValueError:
            continue
        if 0 <= v <= 6:
            out.append(v)
    return tuple(sorted(set(out))) or None


def parse_csv_symbols(spec: Optional[str]) -> list[str]:
    if not spec:
        return []
    return [normalize_symbol(p) for p in spec.split(",") if p.strip()]


# ----------------------------------------------------------------------
# Serialisation
# ----------------------------------------------------------------------

def _bar_dict(row: OhlcvBar | None, fields: tuple[str, ...]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    return {f: getattr(row, f) for f in fields}


def _prediction_dict(
    row: PredictionPoint, fields: tuple[str, ...]
) -> dict[str, Any]:
    days_ago = (row.target_date - row.made_on).days
    out: dict[str, Any] = {
        "made_on": row.made_on.isoformat(),
        "made_on_dow": row.made_on_dow,
        "days_ago": days_ago,
        "horizon_offset": row.horizon_offset,
        "model_id": row.model_id,
        "interval": row.interval,
    }
    for f in fields:
        out[f] = getattr(row, f)
    return out


# ----------------------------------------------------------------------
# Queries
# ----------------------------------------------------------------------

async def _fetch_actual(
    session: AsyncSession, *, ticker: str, interval: str, target_date: datetime.date
) -> Optional[OhlcvBar]:
    """Return the OHLCV bar whose ``ts`` falls on ``target_date`` (UTC).

    Uses a half-open day window so any tz-aware timestamp on that calendar
    day matches.
    """
    start = datetime.datetime.combine(target_date, datetime.time(0, 0, tzinfo=datetime.timezone.utc))
    end = start + datetime.timedelta(days=1)
    row = (
        await session.execute(
            select(OhlcvBar)
            .where(
                and_(
                    OhlcvBar.symbol == ticker,
                    OhlcvBar.interval == interval,
                    OhlcvBar.ts >= start,
                    OhlcvBar.ts < end,
                )
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def by_target(
    *,
    ticker: str,
    target_date: datetime.date,
    interval: str = "1d",
    model_id: Optional[str] = None,
    made_on_dow: Optional[tuple[int, ...]] = None,
    fields: tuple[str, ...] = _DEFAULT_FIELDS,
) -> dict[str, Any]:
    """Every prediction ever made for (``ticker``, ``target_date``) + actual.

    Returns::

        {
          "ticker": ...,
          "target_date": "2026-05-02",
          "interval": "1d",
          "fields": [...],
          "actual": {open, high, low, close, ...} | null,
          "predictions": [
            {made_on, made_on_dow, days_ago, horizon_offset, model_id, ...},
            ...
          ]  # sorted made_on DESC (most recent first)
        }
    """
    sym = normalize_symbol(ticker)
    async with _db.SessionLocal() as session:
        stmt = (
            select(PredictionPoint)
            .where(
                and_(
                    PredictionPoint.ticker == sym,
                    PredictionPoint.target_date == target_date,
                    PredictionPoint.interval == interval,
                )
            )
            .order_by(PredictionPoint.made_on.desc(), PredictionPoint.model_id)
        )
        if model_id:
            stmt = stmt.where(PredictionPoint.model_id == model_id)
        if made_on_dow:
            stmt = stmt.where(PredictionPoint.made_on_dow.in_(made_on_dow))

        pred_rows = (await session.execute(stmt)).scalars().all()
        actual_row = await _fetch_actual(
            session, ticker=sym, interval=interval, target_date=target_date
        )

    return {
        "ticker": sym,
        "target_date": target_date.isoformat(),
        "interval": interval,
        "fields": list(fields),
        "actual": _bar_dict(actual_row, fields),
        "predictions": [_prediction_dict(r, fields) for r in pred_rows],
    }


async def by_horizon(
    *,
    target_date: datetime.date,
    horizons: Iterable[int],
    tickers: Iterable[str],
    interval: str = "1d",
    model_id: Optional[str] = None,
    made_on_dow: Optional[tuple[int, ...]] = None,
    fields: tuple[str, ...] = _DEFAULT_FIELDS,
) -> list[dict[str, Any]]:
    """For each (ticker × horizon), fetch the prediction made N calendar days
    before ``target_date`` plus the actual bar. ``horizons`` are positive
    integers (1 = "made the day before target", 5 = "5 days before").

    Returns a flat list — one row per (ticker, horizon) cell. Missing
    predictions yield rows with ``prediction=null``.
    """
    horizons = sorted(set(h for h in horizons if h > 0))
    syms = [normalize_symbol(t) for t in tickers if t]
    if not syms or not horizons:
        return []

    out: list[dict[str, Any]] = []
    async with _db.SessionLocal() as session:
        for sym in syms:
            actual_row = await _fetch_actual(
                session, ticker=sym, interval=interval, target_date=target_date
            )
            actual = _bar_dict(actual_row, fields)

            for h in horizons:
                made_on = target_date - datetime.timedelta(days=h)
                if made_on_dow is not None and made_on.weekday() not in made_on_dow:
                    out.append(
                        {
                            "ticker": sym,
                            "target_date": target_date.isoformat(),
                            "made_on": made_on.isoformat(),
                            "days_ago": h,
                            "actual": actual,
                            "prediction": None,
                        }
                    )
                    continue

                stmt = (
                    select(PredictionPoint)
                    .where(
                        and_(
                            PredictionPoint.ticker == sym,
                            PredictionPoint.target_date == target_date,
                            PredictionPoint.made_on == made_on,
                            PredictionPoint.interval == interval,
                        )
                    )
                    .order_by(PredictionPoint.created_at.desc())
                    .limit(1)
                )
                if model_id:
                    stmt = stmt.where(PredictionPoint.model_id == model_id)

                pp = (await session.execute(stmt)).scalar_one_or_none()
                out.append(
                    {
                        "ticker": sym,
                        "target_date": target_date.isoformat(),
                        "made_on": made_on.isoformat(),
                        "days_ago": h,
                        "actual": actual,
                        "prediction": _prediction_dict(pp, fields) if pp else None,
                    }
                )
    return out
