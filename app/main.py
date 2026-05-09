"""Read-only public demo backend.

Serves a frozen snapshot of TradingView. No DB, no model, no secrets,
no write paths. The live backend lives on `main`; this `demo` branch is
the strip-down deployed to Railway as the public showcase.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.demo.routes import router as demo_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TradingView Demo",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _cors_origins() -> list[str]:
    raw = (os.environ.get("FRONTEND_ORIGIN") or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "https://tradingv-83b.pages.dev",
        "http://localhost:3000",
        "http://localhost:5173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(demo_router, prefix="/v1/demo")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "demo"}
