"""FRED-backed macro provider — economic series.

Uses the public CSV download endpoint:
``https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series_id>``

No API key required for CSV. Keeps dep surface zero (only ``httpx``,
already in use by ``app.market_data``).
"""
from __future__ import annotations

import csv
import datetime
import io
import logging
from typing import List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class FREDProvider:
    name = "fred"

    async def fetch(
        self, symbol: str, since: Optional[datetime.date] = None
    ) -> List[Tuple[datetime.date, float]]:
        params = {"id": symbol}
        if since is not None:
            params["cosd"] = since.isoformat()  # FRED honors `cosd` as start

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(_FRED_CSV_URL, params=params)
                r.raise_for_status()
                body = r.text
        except Exception as e:  # noqa: BLE001
            logger.warning("FRED fetch failed for %s: %s", symbol, e)
            return []

        return _parse_fred_csv(symbol, body)


def _parse_fred_csv(symbol: str, body: str) -> List[Tuple[datetime.date, float]]:
    """FRED CSV shape:
        DATE,<SERIES_ID>
        2020-01-01,5.5
        2020-01-08,.       <- '.' marks missing observation; drop
        ...
    """
    out: List[Tuple[datetime.date, float]] = []
    reader = csv.reader(io.StringIO(body))
    header = next(reader, None)
    if not header or len(header) < 2:
        return []

    for row in reader:
        if len(row) < 2:
            continue
        date_str, value_str = row[0].strip(), row[1].strip()
        if not date_str or value_str in ("", "."):
            continue
        try:
            d = datetime.date.fromisoformat(date_str)
            v = float(value_str)
        except ValueError:
            continue
        out.append((d, v))
    return out
