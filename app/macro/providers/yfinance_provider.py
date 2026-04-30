"""yfinance-backed macro provider — equities, futures, FX, ETFs.

Reuses the existing yfinance dependency. Returns *close* values only;
macro layer is single-value-per-day by design.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class YFinanceMacroProvider:
    name = "yfinance"

    async def fetch(
        self, symbol: str, since: Optional[datetime.date] = None
    ) -> List[Tuple[datetime.date, float]]:
        # yfinance is sync + blocking; offload to a worker thread.
        return await asyncio.to_thread(_fetch_sync, symbol, since)


def _fetch_sync(
    symbol: str, since: Optional[datetime.date]
) -> List[Tuple[datetime.date, float]]:
    # Import inside the worker so the main event loop doesn't pay the cost
    # on startup, and so tests that monkey-patch can replace this without
    # ever importing yfinance.
    import yfinance as yf  # type: ignore

    period = "max" if since is None else None
    start = None if since is None else since.isoformat()

    try:
        df = yf.download(
            tickers=symbol,
            interval="1d",
            period=period,
            start=start,
            progress=False,
            auto_adjust=False,
            threads=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("yfinance fetch failed for %s: %s", symbol, e)
        return []

    if df is None or df.empty:
        return []

    # MultiIndex when multiple tickers; we always request one but be defensive.
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    if "Close" not in df.columns:
        return []

    out: List[Tuple[datetime.date, float]] = []
    for ts, row in df.iterrows():
        close = row["Close"]
        # yfinance returns NaN for missing observations; drop them.
        try:
            val = float(close)
        except (TypeError, ValueError):
            continue
        if val != val:  # NaN check
            continue
        d = ts.date() if hasattr(ts, "date") else ts
        out.append((d, val))
    return out
