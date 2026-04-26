import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import SETTINGS
from app.core.db import Base, engine

# Ensure models are imported so Base.metadata knows about them.
from app.alerts import models as _alert_models  # noqa: F401
from app.tickers import models as _ticker_models  # noqa: F401
from app.market_data import models as _ohlcv_models  # noqa: F401
from app.analysis import models as _analysis_models  # noqa: F401
from app.sync import models as _sync_models  # noqa: F401
from app.labels import models as _labels_models  # noqa: F401
from app.predictions import models as _predictions_models  # noqa: F401
from app.schedule import models as _schedule_models  # noqa: F401
from app.watchlist import models as _watchlist_models  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        from app.core.config import SETTINGS

        if SETTINGS.KRONOS_ENABLED:
            from app.kronos.real_adapter import activate as activate_kronos

            activate_kronos()

        # Best-effort drain of outbox rows left pending from prior process.
        import asyncio

        from app.sync import service as _sync_service

        if _sync_service.peer_configured():
            asyncio.create_task(_sync_service.drain_outbox())

        # Hourly purge of old completed outbox rows (config-driven retention).
        purge_task = asyncio.create_task(_sync_service.purge_loop(), name="outbox-purge")

        # Daily forecast scheduler (idle until enabled via PUT /v1/schedule).
        from app.schedule import runner as _schedule_runner

        _schedule_runner.start()

        yield

        # Clean shutdown.
        await _schedule_runner.stop()
        purge_task.cancel()

    except Exception as e:
        logger.error("startup error: %s", e)
        raise


app = FastAPI(lifespan=lifespan, title="TradingView Analysis Platform")


def _cors_origins() -> list[str]:
    """Allow-list for the browser-side frontend.

    Production: set ``FRONTEND_ORIGIN`` to one or more comma-separated
    absolute origins (the deployed Lovable / Vercel URLs).

    Local dev: when ``FRONTEND_ORIGIN`` is empty we fall back to the
    common Vite (5173) and Next.js (3000) ports so a developer on the
    laptop can hit the API from a browser without env config.
    """
    raw = (SETTINGS.FRONTEND_ORIGIN or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
