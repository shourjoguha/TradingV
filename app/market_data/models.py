import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class OhlcvBar(Base):
    """OHLCV candlestick bar, deduped on (symbol, interval, ts)."""

    __tablename__ = "ohlcv_bars"

    # Composite primary key — symbol normalized uppercase.
    symbol: Mapped[str] = mapped_column(String(50), primary_key=True)
    interval: Mapped[str] = mapped_column(String(8), primary_key=True)
    ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    # `amount` (turnover) is optional — not every provider reports it. Kronos
    # needs it; we'll compute a fallback (close * volume) if missing.
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
