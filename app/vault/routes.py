"""HTTP routes for the vault proxy.

Forwarders for the indexer's ``/search``, ``/folder-context``, and
``/node/{path}`` endpoints. Read-only. Errors and timeouts are surfaced as
504-on-timeout / 502-on-other-failure so the caller can degrade gracefully
when the indexer sidecar is offline (it lives on the laptop only).
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.core.auth import verify_api_key


logger = logging.getLogger(__name__)

VAULT_INDEXER_URL = os.environ.get("VAULT_INDEXER_URL", "http://localhost:8001")
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("VAULT_INDEXER_TIMEOUT", "10.0"))


router = APIRouter(prefix="/vault", tags=["vault"])


async def _forward_get(path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            r = await client.get(f"{VAULT_INDEXER_URL}{path}", params=params)
            r.raise_for_status()
            return r.json()
    except httpx.TimeoutException as e:
        logger.warning("vault-indexer timeout: %s", e)
        raise HTTPException(504, "vault-indexer did not respond in time") from e
    except httpx.HTTPStatusError as e:
        logger.warning("vault-indexer HTTP %s: %s", e.response.status_code, e)
        raise HTTPException(
            502, f"vault-indexer returned {e.response.status_code}"
        ) from e
    except httpx.HTTPError as e:
        logger.warning("vault-indexer error: %s", e)
        raise HTTPException(502, "vault-indexer unreachable") from e


async def _forward_post(path: str, payload: dict[str, Any]) -> Any:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            r = await client.post(f"{VAULT_INDEXER_URL}{path}", json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.TimeoutException as e:
        logger.warning("vault-indexer timeout: %s", e)
        raise HTTPException(504, "vault-indexer did not respond in time") from e
    except httpx.HTTPStatusError as e:
        logger.warning("vault-indexer HTTP %s: %s", e.response.status_code, e)
        raise HTTPException(
            502, f"vault-indexer returned {e.response.status_code}"
        ) from e
    except httpx.HTTPError as e:
        logger.warning("vault-indexer error: %s", e)
        raise HTTPException(502, "vault-indexer unreachable") from e


# ---------------------------------------------------------------------------
# /v1/vault/search
# ---------------------------------------------------------------------------

@router.get("/search")
async def search(
    q: str = Query(min_length=1),
    k: int = Query(default=8, ge=1, le=50),
    _api_key: str = Depends(verify_api_key),
) -> Any:
    return await _forward_get("/search", params={"q": q, "k": k})


# ---------------------------------------------------------------------------
# /v1/vault/folder-context
# ---------------------------------------------------------------------------

@router.post("/folder-context")
async def folder_context(
    payload: dict[str, Any] = Body(...),
    _api_key: str = Depends(verify_api_key),
) -> Any:
    paths = payload.get("paths") or []
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise HTTPException(400, "payload.paths must be a list of strings")
    return await _forward_post("/folder-context", {"paths": paths})


# ---------------------------------------------------------------------------
# /v1/vault/node/{path}
# ---------------------------------------------------------------------------

@router.get("/node/{path:path}")
async def node(
    path: str,
    _api_key: str = Depends(verify_api_key),
) -> Any:
    return await _forward_get(f"/node/{path}")
