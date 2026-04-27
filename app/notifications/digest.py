"""Daily Telegram digest — Phase 4.

Runs once per day at ``DIGEST_HOUR_UTC``. Posts:
- Top open opportunities (sorted by confidence × predicted_move)
- Unacknowledged drift alerts
- Headline: schedule status + last run summary

When Telegram isn't configured (missing token/chat-id), the loop still runs
but ``send_message`` no-ops. No deploy-time blockers.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Optional

from sqlalchemy import select

from app.accuracy import drift as _drift
from app.core import db as _db
from app.core.config import SETTINGS
from app.notifications import telegram as _telegram

logger = logging.getLogger(__name__)


def _seconds_until_next_digest(now: datetime.datetime, hour_utc: int) -> int:
    """Seconds until the next ``hour_utc`` mark (today or tomorrow)."""
    target_today = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if now < target_today:
        target = target_today
    else:
        target = target_today + datetime.timedelta(days=1)
    return max(60, int((target - now).total_seconds()))


async def _build_digest() -> str:
    """Compose the markdown digest body."""
    lines: list[str] = ["*Daily Kronos digest*"]

    # Open opportunities (lazy import to avoid cycles before Phase 3 lands).
    try:
        from app.opportunities import service as _opps_service

        opps = await _opps_service.list_opportunities(status="open", limit=10)
    except (ImportError, Exception) as e:  # noqa: BLE001
        logger.debug("digest: opportunities not yet available (%s)", e)
        opps = []

    if opps:
        lines.append("\n*Top opportunities*")
        for o in opps[:5]:
            arrow = "📈" if o["kind"] == "buy" else "📉"
            lines.append(
                f"{arrow} `{o['ticker']}` "
                f"{o['kind'].upper()} ({o['rule_label']}): "
                f"predicted {o['predicted_move_pct'] * 100:+.2f}% "
                f"· conf {o['confidence']:.2f}"
            )
    else:
        lines.append("\n_No open opportunities._")

    # Open drift alerts.
    drifts = await _drift.list_open_alerts()
    if drifts:
        lines.append("\n*Drift alerts*")
        for d in drifts[:5]:
            lines.append(
                f"⚠️ `{d['ticker']}` @ +{d['horizon_offset']}d "
                f"({d['model_id']}): recent MAPE "
                f"{d['recent_mape'] * 100:.2f}% vs all-time "
                f"{d['all_time_mape'] * 100:.2f}% ({d['ratio']:.2f}×)"
            )

    # Schedule + last-run line.
    try:
        from app.schedule.models import ScheduleConfig

        async with _db.SessionLocal() as session:
            cfg = await session.scalar(select(ScheduleConfig).limit(1))
            if cfg:
                state = "enabled" if cfg.enabled else "disabled"
                last = (
                    f"last_run={cfg.last_run_status}"
                    if cfg.last_run_status
                    else "no runs yet"
                )
                lines.append(f"\n_Schedule: {state} · {last}_")
    except Exception as e:  # noqa: BLE001
        logger.debug("digest: schedule snapshot failed (%s)", e)

    return "\n".join(lines)


async def send_digest_now() -> bool:
    """Compose + send digest immediately. Returns True if sent."""
    body = await _build_digest()
    return await _telegram.send_message(body)


async def digest_loop(*, stop_event: Optional[asyncio.Event] = None) -> None:
    """Sleep until next ``DIGEST_HOUR_UTC``, send, repeat. Cancellation-safe."""
    logger.info("notifications.digest_loop started (hour=%d UTC)", SETTINGS.DIGEST_HOUR_UTC)
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        wait_s = _seconds_until_next_digest(now, SETTINGS.DIGEST_HOUR_UTC)
        try:
            if stop_event is not None:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_s)
                if stop_event.is_set():
                    logger.info("digest_loop stopping (signal)")
                    return
            else:
                await asyncio.sleep(wait_s)
        except asyncio.TimeoutError:
            pass  # Wakeup time reached; fall through to send.
        except asyncio.CancelledError:
            raise

        try:
            await send_digest_now()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("digest send failed: %s", e)
