"""CORS preflight + actual-request behaviour.

Exercises the middleware added in app/main.py for the browser-side
frontend (Lovable / Vercel / local Vite).
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_cors_preflight_allows_localhost_dev_origin(client):
    """Local Vite dev (5173) must work with no FRONTEND_ORIGIN env set."""
    r = await client.options(
        "/v1/watchlist",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )
    assert r.status_code in (200, 204), r.text
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "GET" in r.headers.get("access-control-allow-methods", "")


@pytest.mark.asyncio
async def test_cors_preflight_allows_nextjs_dev_origin(client):
    """Local Next.js dev (3000) must work with no FRONTEND_ORIGIN env set."""
    r = await client.options(
        "/v1/watchlist",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_actual_request_includes_cors_header(client):
    """Authenticated request from a dev origin gets CORS headers on the response."""
    r = await client.get(
        "/v1/watchlist",
        headers={"X-API-Key": "test-key", "Origin": "http://localhost:5173"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_unknown_origin_not_allowed(client):
    """An origin not in the allow-list gets no CORS headers (request still
    succeeds at the HTTP level — browser is the enforcer)."""
    r = await client.options(
        "/v1/watchlist",
        headers={
            "Origin": "https://attacker.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI returns 400 when the preflight fails origin check.
    assert r.headers.get("access-control-allow-origin") != "https://attacker.example.com"


@pytest.mark.asyncio
async def test_health_includes_cors(client):
    """Health endpoint, useful as a CORS-pingable probe from the toggle."""
    r = await client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
