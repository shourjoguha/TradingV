"""Tests for /v1/vault/* — read-only proxy to the vault-indexer sidecar.

The indexer runs on port 8001 in production. Tests mock httpx so we exercise
the auth/validation/error-mapping logic without depending on a live sidecar.
"""
from __future__ import annotations

import httpx
import pytest

from app.vault import routes as vault_routes


HEADERS = {"X-API-Key": "test-key"}


class _MockResponse:
    def __init__(self, *, status_code: int = 200, json_payload=None):
        self.status_code = status_code
        self._json = json_payload or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )


class _MockClient:
    def __init__(
        self,
        get_response=None,
        post_response=None,
        get_exc=None,
        post_exc=None,
    ):
        self._get_response = get_response
        self._post_response = post_response
        self._get_exc = get_exc
        self._post_exc = post_exc
        self.last_get_url = None
        self.last_get_params = None
        self.last_post_url = None
        self.last_post_json = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, url, params=None):
        self.last_get_url = url
        self.last_get_params = params
        if self._get_exc:
            raise self._get_exc
        return self._get_response

    async def post(self, url, json=None):
        self.last_post_url = url
        self.last_post_json = json
        if self._post_exc:
            raise self._post_exc
        return self._post_response


@pytest.fixture
def patch_httpx(monkeypatch):
    holder: dict = {}

    def factory(**kwargs):
        client = _MockClient(**kwargs)
        holder["client"] = client

        def _make(*_args, **_kwargs):
            return client

        monkeypatch.setattr(vault_routes.httpx, "AsyncClient", _make)
        return client

    return factory


# ---------------------------------------------------------------------------
# /search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_forwards_query_and_k(client, patch_httpx):
    mock = patch_httpx(
        get_response=_MockResponse(json_payload={"results": [{"path": "x.md"}]})
    )
    r = await client.get(
        "/v1/vault/search", params={"q": "META", "k": 4}, headers=HEADERS
    )
    assert r.status_code == 200
    assert r.json() == {"results": [{"path": "x.md"}]}
    assert mock.last_get_url.endswith("/search")
    assert mock.last_get_params == {"q": "META", "k": 4}


@pytest.mark.asyncio
async def test_search_requires_q(client):
    r = await client.get("/v1/vault/search", headers=HEADERS)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_search_clamps_k(client):
    r = await client.get(
        "/v1/vault/search", params={"q": "x", "k": 999}, headers=HEADERS
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_search_indexer_timeout_returns_504(client, patch_httpx):
    patch_httpx(get_exc=httpx.TimeoutException("slow"))
    r = await client.get(
        "/v1/vault/search", params={"q": "META"}, headers=HEADERS
    )
    assert r.status_code == 504


@pytest.mark.asyncio
async def test_search_indexer_5xx_maps_to_502(client, patch_httpx):
    patch_httpx(get_response=_MockResponse(status_code=503))
    r = await client.get(
        "/v1/vault/search", params={"q": "META"}, headers=HEADERS
    )
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_search_indexer_unreachable_maps_to_502(client, patch_httpx):
    patch_httpx(get_exc=httpx.ConnectError("nope"))
    r = await client.get(
        "/v1/vault/search", params={"q": "META"}, headers=HEADERS
    )
    assert r.status_code == 502


# ---------------------------------------------------------------------------
# /folder-context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_folder_context_forwards_paths(client, patch_httpx):
    mock = patch_httpx(
        post_response=_MockResponse(json_payload={"items": []})
    )
    r = await client.post(
        "/v1/vault/folder-context",
        json={"paths": ["The Street/snapshots/2026-05-08/_index.md"]},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert mock.last_post_json == {
        "paths": ["The Street/snapshots/2026-05-08/_index.md"]
    }


@pytest.mark.asyncio
async def test_folder_context_rejects_non_string_paths(client):
    r = await client.post(
        "/v1/vault/folder-context",
        json={"paths": [123, None]},
        headers=HEADERS,
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /node/{path}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_node_forwards_path_with_slashes(client, patch_httpx):
    mock = patch_httpx(
        get_response=_MockResponse(json_payload={"body_md": "# hi"})
    )
    r = await client.get(
        "/v1/vault/node/The Street/snapshots/2026-05-08/_index.md",
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json() == {"body_md": "# hi"}
    assert mock.last_get_url.endswith(
        "/node/The Street/snapshots/2026-05-08/_index.md"
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_required_for_search(client):
    r = await client.get("/v1/vault/search", params={"q": "x"})
    assert r.status_code in (401, 403)
