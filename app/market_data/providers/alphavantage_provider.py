"""Alpha Vantage OHLCV provider — additive alternative/backup to yfinance.

Implements the same ``Provider`` contract (`providers/base.py`) so it slots into
the existing registry with ``registry.register(...)``. It is NOT registered by
default — yfinance stays primary. Enable it explicitly at boot when an API key
is configured (see ``app/main.py``).

Self-reporting: when ``ALPHAVANTAGE_API_KEY`` is unset, ``supports()`` returns
False so ``registry.resolve`` skips this provider gracefully instead of erroring.
Free-tier Alpha Vantage is rate-limited (a few calls/min); this is a backup,
not a bulk source.
"""
from __future__ import annotations

import datetime
import logging
from typing import List

from app.market_data.providers.base import Bar, UnsupportedRequest

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.alphavantage.co/query"

# Canonical interval -> (function, interval-param). Intraday needs the param;
# daily/weekly are their own functions.
_INTRADAY = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "60min"}
_SUPPORTED_ASSETS = {"stock", "etf"}


class AlphaVantageProvider:
    """Alpha Vantage-backed provider. Stocks and ETFs only."""

    name = "alphavantage"

    def __init__(self, api_key: str | None = None) -> None:
        # Read once at construction; empty key => provider self-disables.
        if api_key is None:
            from app.core.config import SETTINGS

            api_key = SETTINGS.ALPHAVANTAGE_API_KEY
        self._api_key = (api_key or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def supports(self, asset_class: str, interval: str) -> bool:
        if not self.configured:
            return False
        return asset_class in _SUPPORTED_ASSETS and (
            interval in _INTRADAY or interval in ("1d", "1w")
        )

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

        params = {"symbol": symbol, "apikey": self._api_key, "outputsize": "full"}
        if interval in _INTRADAY:
            params["function"] = "TIME_SERIES_INTRADAY"
            params["interval"] = _INTRADAY[interval]
            series_key_hint = f"Time Series ({_INTRADAY[interval]})"
        elif interval == "1d":
            params["function"] = "TIME_SERIES_DAILY"
            series_key_hint = "Time Series (Daily)"
        else:  # 1w
            params["function"] = "TIME_SERIES_WEEKLY"
            series_key_hint = "Weekly Time Series"

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.get(_BASE_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()

        # Alpha Vantage surfaces rate-limit / error states as JSON, not HTTP codes.
        if "Note" in payload or "Information" in payload:
            logger.warning("alphavantage throttled/info for %s: %s", symbol, payload)
            return []
        if "Error Message" in payload:
            logger.warning("alphavantage error for %s: %s", symbol, payload["Error Message"])
            return []

        series = payload.get(series_key_hint)
        if series is None:
            # Fall back to the first "Time Series"-ish key if the hint missed.
            series = next(
                (v for k, v in payload.items() if "Time Series" in k or "Weekly" in k),
                None,
            )
        if not series:
            return []

        return _parse_series(series, interval, start, end)


def _parse_series(
    series: dict,
    interval: str,
    start: datetime.datetime | None,
    end: datetime.datetime | None,
) -> List[Bar]:
    intraday = interval in _INTRADAY
    out: List[Bar] = []
    for ts_str, row in series.items():
        try:
            if intraday:
                ts = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            else:
                ts = datetime.datetime.strptime(ts_str, "%Y-%m-%d")
            ts = ts.replace(tzinfo=datetime.timezone.utc)
            if start and ts < start:
                continue
            if end and ts > end:
                continue
            out.append(
                Bar(
                    ts=ts,
                    open=float(row["1. open"]),
                    high=float(row["2. high"]),
                    low=float(row["3. low"]),
                    close=float(row["4. close"]),
                    volume=float(row.get("5. volume", 0.0)),
                    amount=None,
                )
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("alphavantage row skipped (%s): %s", ts_str, e)
    out.sort(key=lambda b: b.ts)
    return out
