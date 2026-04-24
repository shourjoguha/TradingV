"""HTTP client that posts tickers to the PEER backend.

Single-purpose — no retry logic here. Callers (outbox drain) own retries.
Failures return False + reason string so the outbox row can be updated.
"""
from __future__ import annotations

import logging
from typing import Tuple

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


async def push_ticker(
    *, peer_url: str, api_key: str, symbol: str, asset_class: str
) -> Tuple[bool, str | None]:
    """POST one ticker to `{peer_url}/v1/tickers`. Returns (ok, error_message)."""
    url = peer_url.rstrip("/") + "/v1/tickers"
    payload = {"symbol": symbol, "asset_class": asset_class}
    headers = {"X-API-Key": api_key}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if 200 <= resp.status_code < 300:
            return True, None
        return False, f"http_{resp.status_code}: {resp.text[:200]}"
    except httpx.HTTPError as e:
        return False, f"{type(e).__name__}: {e}"
