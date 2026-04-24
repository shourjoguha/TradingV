"""Provider registry. Routes requests to the right provider per asset class."""
from __future__ import annotations

from typing import List

from app.market_data.providers.base import Provider, UnsupportedRequest
from app.market_data.providers.yfinance_provider import YFinanceProvider

# Module-level registry. Tests can monkey-patch _PROVIDERS to inject fakes.
_PROVIDERS: List[Provider] = [YFinanceProvider()]


def providers() -> List[Provider]:
    return list(_PROVIDERS)


def resolve(asset_class: str, interval: str) -> Provider:
    for p in _PROVIDERS:
        if p.supports(asset_class, interval):
            return p
    raise UnsupportedRequest(asset_class=asset_class, interval=interval)


def register(provider: Provider, *, prepend: bool = False) -> None:
    """Register an additional provider. Prepend to take priority over defaults."""
    if prepend:
        _PROVIDERS.insert(0, provider)
    else:
        _PROVIDERS.append(provider)


def reset_to_defaults() -> None:
    """Test helper: restore the default provider list."""
    global _PROVIDERS
    _PROVIDERS = [YFinanceProvider()]
