"""HTTP clients that push to the PEER backend.

Single-purpose — no retry logic here. Callers (outbox drain) own retries.
Failures return False + reason string so the outbox row can be updated.
"""
from __future__ import annotations

import logging
from typing import Any, Tuple

import httpx

logger = logging.getLogger(__name__)

# Result snapshots can be ~50KB+ JSON; allow more time than ticker pushes.
_TICKER_TIMEOUT = httpx.Timeout(10.0, connect=3.0)
_RESULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


async def push_ticker(
    *, peer_url: str, api_key: str, symbol: str, asset_class: str
) -> Tuple[bool, str | None]:
    """POST one ticker to ``{peer_url}/v1/tickers``. Returns (ok, error_message)."""
    url = peer_url.rstrip("/") + "/v1/tickers"
    payload = {"symbol": symbol, "asset_class": asset_class}
    headers = {"X-API-Key": api_key}
    try:
        async with httpx.AsyncClient(timeout=_TICKER_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if 200 <= resp.status_code < 300:
            return True, None
        return False, f"http_{resp.status_code}: {resp.text[:200]}"
    except httpx.HTTPError as e:
        return False, f"{type(e).__name__}: {e}"


async def _post_json(
    *, peer_url: str, path: str, api_key: str, payload: dict[str, Any],
    timeout: httpx.Timeout,
) -> Tuple[bool, str | None]:
    url = peer_url.rstrip("/") + path
    headers = {"X-API-Key": api_key}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if 200 <= resp.status_code < 300:
            return True, None
        return False, f"http_{resp.status_code}: {resp.text[:200]}"
    except httpx.HTTPError as e:
        return False, f"{type(e).__name__}: {e}"


async def push_watchlist(
    *, peer_url: str, api_key: str, payload: dict[str, Any]
) -> Tuple[bool, str | None]:
    """POST watchlist diff to ``{peer_url}/v1/watchlist/import``.

    Payload shape::

        {"action": "upsert" | "delete",
         "symbol": "AAPL",
         "notes": "...",     # only on upsert
         "added_at": "ISO"}  # only on upsert; receiver may ignore
    """
    return await _post_json(
        peer_url=peer_url, path="/v1/watchlist/import",
        api_key=api_key, payload=payload, timeout=_TICKER_TIMEOUT,
    )


async def push_schedule(
    *, peer_url: str, api_key: str, payload: dict[str, Any]
) -> Tuple[bool, str | None]:
    """POST schedule_config snapshot to ``{peer_url}/v1/schedule/import``.

    Payload is the full singleton-row dict (last-write-wins). Receiver
    overwrites everything except its own runtime-only fields
    (``pending_run``, ``last_run_*``, ``next_run_at``).
    """
    return await _post_json(
        peer_url=peer_url, path="/v1/schedule/import",
        api_key=api_key, payload=payload, timeout=_TICKER_TIMEOUT,
    )


async def push_label(
    *, peer_url: str, api_key: str, payload: dict[str, Any]
) -> Tuple[bool, str | None]:
    """POST a single label change to ``{peer_url}/v1/labels/import``.

    Payload shape::

        {"action": "upsert" | "delete",
         "symbol": "AAPL",
         "key": "sector",
         "value": <any JSON>}   # only on upsert
    """
    return await _post_json(
        peer_url=peer_url, path="/v1/labels/import",
        api_key=api_key, payload=payload, timeout=_TICKER_TIMEOUT,
    )


async def push_tv_context(
    *, peer_url: str, api_key: str, payload: dict[str, Any]
) -> Tuple[bool, str | None]:
    """POST one tv_context_item snapshot to ``{peer_url}/v1/tv-context/import``.

    Receiver is idempotent on ``payload['id']`` — duplicate posts return
    200. Skipped for kind='screenshot' (vault path is environment-specific).
    """
    return await _post_json(
        peer_url=peer_url, path="/v1/tv-context/import",
        api_key=api_key, payload=payload, timeout=_TICKER_TIMEOUT,
    )


async def push_result(
    *, peer_url: str, api_key: str, payload: dict[str, Any]
) -> Tuple[bool, str | None]:
    """POST one job snapshot to ``{peer_url}/v1/analysis/import``.

    Receiver is idempotent on ``payload['job']['id']`` — duplicate posts
    return 200. Returns (ok, error_message).
    """
    url = peer_url.rstrip("/") + "/v1/analysis/import"
    headers = {"X-API-Key": api_key}
    try:
        async with httpx.AsyncClient(timeout=_RESULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if 200 <= resp.status_code < 300:
            return True, None
        return False, f"http_{resp.status_code}: {resp.text[:200]}"
    except httpx.HTTPError as e:
        return False, f"{type(e).__name__}: {e}"
