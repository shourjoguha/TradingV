import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(50))
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    alert_type: Mapped[str] = mapped_column(String(50))
    payload_json: Mapped[dict] = mapped_column(JSON)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
