from __future__ import annotations

import asyncio
import datetime
import logging
from typing import List

from app.market_data.providers.base import Bar, Provider, UnsupportedRequest

logger = logging.getLogger(__name__)

# Canonical → yfinance interval code.
# yfinance supports: 1m, 2m, 5m, 15m, 30m, 60m/1h, 90m, 1d, 5d, 1wk, 1mo, 3mo.
_YF_INTERVAL = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "1d": "1d",
    "1w": "1wk",
}

# yfinance enforces max-range per interval. These are conservative defaults.
_DEFAULT_RANGE_DAYS = {
    "1m": 7,
    "5m": 60,
    "15m": 60,
    "30m": 60,
    "1h": 730,
    "1d": 3650,
    "1w": 3650,
}

_SUPPORTED_ASSETS = {"stock", "etf"}


class YFinanceProvider:
    """yfinance-backed provider. Stocks and ETFs only.

    Crypto is out of scope in v1 — yfinance does return crypto via `BTC-USD`
    but the data quality and timeliness vary. When we add a crypto provider
    (e.g. Binance), this provider will stay stock/ETF only.
    """

    name = "yfinance"

    def supports(self, asset_class: str, interval: str) -> bool:
        return asset_class in _SUPPORTED_ASSETS and interval in _YF_INTERVAL

    async def fetch_ohlcv(
        self,
        symbol: str,
        asset_class: str,
        interval: str,
        start: datetime.datetime | None = None,
        end: datetime.datetime | None = None,
    ) -> List[Bar]:
        if not self.supports(asset_class, interval):
            raise UnsupportedRequest(asset_class=asset_class, interval=interval)

        yf_interval = _YF_INTERVAL[interval]
        if end is None:
            end = datetime.datetime.now(datetime.timezone.utc)
        if start is None:
            start = end - datetime.timedelta(days=_DEFAULT_RANGE_DAYS[interval])

        # yfinance is sync + blocking; run in a worker thread.
        return await asyncio.to_thread(
            _fetch_sync, symbol, yf_interval, start, end
        )


def _fetch_sync(
    symbol: str,
    yf_interval: str,
    start: datetime.datetime,
    end: datetime.datetime,
) -> List[Bar]:
    # Import inside the worker so the main event loop doesn't pay the cost
    # on startup, and so tests that monkey-patch the provider don't need yf.
    import yfinance as yf  # type: ignore

    df = yf.download(
        tickers=symbol,
        interval=yf_interval,
        start=start,
        end=end,
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if df is None or df.empty:
        return []

    # yfinance returns MultiIndex columns when multiple tickers; we request one.
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    out: List[Bar] = []
    for ts, row in df.iterrows():
        # Ensure UTC tz-aware.
        ts_utc = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        try:
            out.append(
                Bar(
                    ts=ts_utc.to_pydatetime(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                    amount=None,
                )
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("yfinance row skipped: %s", e)
    out.sort(key=lambda b: b.ts)
    return out
