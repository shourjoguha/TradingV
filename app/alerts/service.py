import logging
from typing import List

from sqlalchemy import select

from app.alerts.models import Alert
from app.alerts.schemas import AlertCreate
from app.core import db as _db
from app.tickers import service as tickers_service

logger = logging.getLogger(__name__)


async def save_alert(alert_data: AlertCreate) -> None:
    try:
        async with _db.SessionLocal() as session:
            session.add(
                Alert(
                    ticker=alert_data.ticker,
                    alert_type=alert_data.alert_type,
                    payload_json=alert_data.payload_json,
                )
            )
            # Upsert into ticker registry in the same transaction.
            await tickers_service.upsert_ticker(
                session, alert_data.ticker, source="alert"
            )
            await session.commit()
    except Exception as e:
        logger.error("save_alert failed: %s", e)
        return

    # Phase 1 fan-out: when the Pine alert tags itself source='tradingview',
    # also persist a tv_context_items row (deduped within rolling window) so
    # the research/ask + hypothesis-eval gating layer can retrieve it. Alert
    # row is always created (notification semantic); tv_context dedupes
    # (retrieval semantic) — the two correctly diverge.
    payload = alert_data.payload_json or {}
    source = (
        payload.get("source")
        if isinstance(payload, dict)
        else None
    ) or "tradingview"  # default: assume TV unless explicitly other
    if source != "tradingview":
        return
    try:
        from app.tv_context import service as tvc_service

        async with _db.SessionLocal() as session:
            await tvc_service.ingest_webhook(
                session=session,
                ticker=alert_data.ticker,
                alert_type=alert_data.alert_type,
                payload_json=payload,
                source=source,
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("tv_context fan-out failed: %s", e)


async def fetch_unread_and_mark_read() -> List[Alert]:
    async with _db.SessionLocal() as session:
        result = await session.execute(select(Alert).where(Alert.is_read == False))  # noqa: E712
        alerts = list(result.scalars().all())
        if alerts:
            for a in alerts:
                a.is_read = True
            await session.commit()
        return alerts
