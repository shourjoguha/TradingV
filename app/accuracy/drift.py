"""Drift detection — Phase 1.3.

Compares recent-window MAPE to all-time MAPE per ``(ticker, horizon, model)``.
Flags when ratio exceeds threshold AND both windows have minimum sample counts.

Idempotent: while an open ``DriftAlert`` row exists for a pair, no duplicate
is created. Acknowledging via the ack route clears the way for a future flag.

Posts to Telegram on flag (best-effort, non-blocking).
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accuracy.models import DriftAlert, PredictionAccuracy
from app.core import db as _db
from app.core.config import SETTINGS
from app.notifications import telegram as _telegram

logger = logging.getLogger(__name__)

_DEFAULT_TICK_SECONDS = 60 * 60 * 24  # daily — drift evaluates same actuals as accuracy; matched cadence (was 6h pre-2026-05-16)


async def detect_drift(
    *,
    now: Optional[datetime.datetime] = None,
    notify: bool = True,
) -> list[DriftAlert]:
    """Scan all (ticker, horizon, model) groups; flag those that exceed the
    drift threshold.

    Returns the list of newly created ``DriftAlert`` rows. Skips groups that
    already have an unacknowledged open alert.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    recent_cutoff = now - datetime.timedelta(days=SETTINGS.DRIFT_RECENT_WINDOW_DAYS)
    threshold = SETTINGS.DRIFT_RATIO_THRESHOLD
    min_recent = SETTINGS.DRIFT_MIN_RECENT_SAMPLES
    min_all_time = SETTINGS.DRIFT_MIN_ALL_TIME_SAMPLES

    new_alerts: list[DriftAlert] = []

    async with _db.SessionLocal() as session:
        # Discover groups with enough all-time samples to even consider.
        groups_stmt = (
            select(
                PredictionAccuracy.ticker,
                PredictionAccuracy.horizon_offset,
                PredictionAccuracy.model_id,
                func.count(PredictionAccuracy.id).label("n_all"),
                func.avg(PredictionAccuracy.abs_error_pct).label("mape_all"),
            )
            .group_by(
                PredictionAccuracy.ticker,
                PredictionAccuracy.horizon_offset,
                PredictionAccuracy.model_id,
            )
            .having(func.count(PredictionAccuracy.id) >= min_all_time)
        )
        groups = (await session.execute(groups_stmt)).all()

        for ticker, horizon, mid, n_all, mape_all in groups:
            if mape_all is None or mape_all == 0:
                continue

            recent_stmt = select(
                func.count(PredictionAccuracy.id),
                func.avg(PredictionAccuracy.abs_error_pct),
            ).where(
                PredictionAccuracy.ticker == ticker,
                PredictionAccuracy.horizon_offset == horizon,
                PredictionAccuracy.model_id == mid,
                PredictionAccuracy.evaluated_at >= recent_cutoff,
            )
            n_recent, mape_recent = (await session.execute(recent_stmt)).one()
            if n_recent is None or n_recent < min_recent:
                continue
            if mape_recent is None:
                continue

            ratio = float(mape_recent) / float(mape_all)
            if ratio < threshold:
                continue

            # Open alert already exists? Skip — idempotent.
            existing_stmt = select(DriftAlert.id).where(
                DriftAlert.ticker == ticker,
                DriftAlert.horizon_offset == horizon,
                DriftAlert.model_id == mid,
                DriftAlert.acknowledged_at.is_(None),
            )
            if await session.scalar(existing_stmt) is not None:
                continue

            alert = DriftAlert(
                ticker=ticker,
                horizon_offset=horizon,
                model_id=mid,
                recent_mape=float(mape_recent),
                all_time_mape=float(mape_all),
                ratio=ratio,
                recent_sample_count=int(n_recent),
                all_time_sample_count=int(n_all),
            )
            session.add(alert)
            new_alerts.append(alert)
            logger.info(
                "drift detected: %s@%dd (%s) recent=%.4f all=%.4f ratio=%.2f",
                ticker,
                horizon,
                mid,
                mape_recent,
                mape_all,
                ratio,
            )

        await session.commit()

    if notify and new_alerts:
        await _notify_drifts(new_alerts)

    return new_alerts


async def _notify_drifts(alerts: list[DriftAlert]) -> None:
    """Best-effort Telegram message for each new drift alert."""
    if not _telegram.configured():
        return
    lines = ["*Drift detected*"]
    for a in alerts:
        lines.append(
            f"• `{a.ticker}` @ +{a.horizon_offset}d ({a.model_id}) "
            f"— recent MAPE {a.recent_mape * 100:.2f}% vs all-time "
            f"{a.all_time_mape * 100:.2f}% ({a.ratio:.2f}× degradation, "
            f"n_recent={a.recent_sample_count})"
        )
    await _telegram.send_message("\n".join(lines))


async def detector_loop(
    *, tick_seconds: int = _DEFAULT_TICK_SECONDS, stop_event: Optional[asyncio.Event] = None
) -> None:
    """Long-lived task. Calls :func:`detect_drift` every tick. Cancellation-safe."""
    logger.info("accuracy.drift.detector_loop started (tick=%ss)", tick_seconds)
    while True:
        try:
            new = await detect_drift()
            if new:
                logger.info("drift.detector: %d new alerts", len(new))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("drift.detector tick failed: %s", e)

        try:
            if stop_event is not None:
                await asyncio.wait_for(stop_event.wait(), timeout=tick_seconds)
                if stop_event.is_set():
                    logger.info("drift.detector_loop stopping (signal)")
                    return
            else:
                await asyncio.sleep(tick_seconds)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise


# ----------------------------------------------------------------------
# Read paths for the dashboard banner + ack route
# ----------------------------------------------------------------------


async def list_open_alerts() -> list[dict]:
    async with _db.SessionLocal() as session:
        stmt = (
            select(DriftAlert)
            .where(DriftAlert.acknowledged_at.is_(None))
            .order_by(DriftAlert.flagged_at.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "ticker": r.ticker,
                "horizon_offset": r.horizon_offset,
                "model_id": r.model_id,
                "recent_mape": r.recent_mape,
                "all_time_mape": r.all_time_mape,
                "ratio": r.ratio,
                "recent_sample_count": r.recent_sample_count,
                "all_time_sample_count": r.all_time_sample_count,
                "flagged_at": r.flagged_at.isoformat(),
                "acknowledged_at": None,
            }
            for r in rows
        ]


async def acknowledge_alert(alert_id: str) -> bool:
    """Set acknowledged_at on one alert. Returns True if found and updated."""
    async with _db.SessionLocal() as session:
        alert = await session.get(DriftAlert, alert_id)
        if alert is None or alert.acknowledged_at is not None:
            return False
        alert.acknowledged_at = datetime.datetime.now(datetime.timezone.utc)
        await session.commit()
        return True
