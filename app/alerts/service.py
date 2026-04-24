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


async def fetch_unread_and_mark_read() -> List[Alert]:
    async with _db.SessionLocal() as session:
        result = await session.execute(select(Alert).where(Alert.is_read == False))  # noqa: E712
        alerts = list(result.scalars().all())
        if alerts:
            for a in alerts:
                a.is_read = True
            await session.commit()
        return alerts
