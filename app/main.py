import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
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

        # Daily forecast scheduler (idle until enabled via PUT /v1/schedule).
        from app.schedule import runner as _schedule_runner

        _schedule_runner.start()

        yield

        # Clean shutdown.
        await _schedule_runner.stop()

    except Exception as e:
        logger.error("startup error: %s", e)
        raise


app = FastAPI(lifespan=lifespan, title="TradingView Analysis Platform")
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
