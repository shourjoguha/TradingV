from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import List, Protocol, Tuple


@dataclass(frozen=True)
class Bar:
    ts: datetime.datetime  # tz-aware UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None


class Provider(Protocol):
    """Canonical market data provider contract.

    Implementations translate canonical intervals to vendor codes, fetch, and
    return a list of Bar in ascending ts order. No DB access here — that's the
    service's job.
    """

    name: str

    def supports(self, asset_class: str, interval: str) -> bool: ...

    async def fetch_ohlcv(
        self,
        symbol: str,
        asset_class: str,
        interval: str,
        start: datetime.datetime | None = None,
        end: datetime.datetime | None = None,
    ) -> List[Bar]: ...


class ProviderError(Exception):
    """Raised when a provider cannot satisfy a request."""


@dataclass(frozen=True)
class UnsupportedRequest(ProviderError):
    asset_class: str
    interval: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"unsupported asset_class={self.asset_class} interval={self.interval}"
