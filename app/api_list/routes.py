"""/v1/api-list — discovery endpoint for configured data sources.

Enumerates OHLCV price providers (from the live market-data registry) plus the
agent data feeds, each annotated with ``enabled`` and ``configured`` (API key
present) so a missing key is visible at a glance rather than failing silently
at fetch time.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import verify_api_key
from app.core.config import SETTINGS
from app.market_data import registry as md_registry
from app.market_data.intervals import CANONICAL_INTERVALS

router = APIRouter(tags=["api_list"])

_ASSET_CLASSES = ("stock", "etf", "crypto")


class ProviderEntry(BaseModel):
    name: str
    category: str  # "ohlcv" | "agent_feed"
    enabled: bool
    configured: bool
    asset_classes: List[str] = []
    intervals: List[str] = []
    notes: Optional[str] = None


class ApiListResponse(BaseModel):
    ohlcv_providers: List[ProviderEntry]
    agent_feeds: List[ProviderEntry]


def _support_matrix(provider) -> tuple[list[str], list[str]]:
    """Probe a provider's supports() across the canonical grid."""
    assets = [a for a in _ASSET_CLASSES if any(
        _safe_supports(provider, a, i) for i in CANONICAL_INTERVALS
    )]
    intervals = [i for i in CANONICAL_INTERVALS if any(
        _safe_supports(provider, a, i) for a in _ASSET_CLASSES
    )]
    return assets, intervals


def _safe_supports(provider, asset_class: str, interval: str) -> bool:
    try:
        return bool(provider.supports(asset_class, interval))
    except Exception:  # noqa: BLE001
        return False


def _ohlcv_providers() -> List[ProviderEntry]:
    out: List[ProviderEntry] = []
    for p in md_registry.providers():
        assets, intervals = _support_matrix(p)
        # `configured` defaults to True for providers with no key concept
        # (e.g. yfinance); key-gated providers expose a `.configured` flag.
        configured = bool(getattr(p, "configured", True))
        out.append(
            ProviderEntry(
                name=getattr(p, "name", p.__class__.__name__),
                category="ohlcv",
                enabled=True,  # presence in the registry == enabled
                configured=configured,
                asset_classes=assets,
                intervals=intervals,
            )
        )
    return out


def _agent_feeds() -> List[ProviderEntry]:
    """Agent-lane data feeds. These are TradingAgents analyst inputs, not OHLCV
    providers, so they're listed as a separate category. `configured` reflects
    whether the relevant API key is present in settings."""
    feeds = [
        ("alpha_vantage_fundamentals", bool(SETTINGS.ALPHAVANTAGE_API_KEY), "Fundamentals / news via Alpha Vantage"),
        ("finnhub", bool(SETTINGS.FINNHUB_API_KEY), "News + company data"),
        ("reddit", bool(SETTINGS.REDDIT_CLIENT_ID and SETTINGS.REDDIT_CLIENT_SECRET), "Social sentiment"),
        ("stocktwits", True, "Social sentiment (public, keyless)"),
    ]
    return [
        ProviderEntry(
            name=name,
            category="agent_feed",
            enabled=SETTINGS.AGENTS_ENABLED,
            configured=configured,
            notes=notes,
        )
        for name, configured, notes in feeds
    ]


@router.get("/api-list", response_model=ApiListResponse)
async def api_list(_api_key: str = Depends(verify_api_key)):
    return ApiListResponse(
        ohlcv_providers=_ohlcv_providers(),
        agent_feeds=_agent_feeds(),
    )
