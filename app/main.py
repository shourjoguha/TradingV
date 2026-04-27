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
from app.accuracy import models as _accuracy_models  # noqa: F401
from app.opportunities import models as _opportunities_models  # noqa: F401
from app.trades import models as _trades_models  # noqa: F401
from app.market_data import derived as _derived_models  # noqa: F401
from app.queue import models as _queue_models  # noqa: F401

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

        # Hourly accuracy evaluator — fills prediction_accuracy as predictions
        # elapse and actuals land in ohlcv_bars. Idempotent; safe to interrupt.
        from app.accuracy import drift as _drift, service as _accuracy_service

        accuracy_stop = asyncio.Event()
        accuracy_task = asyncio.create_task(
            _accuracy_service.evaluator_loop(stop_event=accuracy_stop),
            name="accuracy-evaluator",
        )

        # 6-hourly drift detector — flags pairs whose recent MAPE has degraded
        # past DRIFT_RATIO_THRESHOLD vs all-time. Posts to Telegram if configured.
        drift_stop = asyncio.Event()
        drift_task = asyncio.create_task(
            _drift.detector_loop(stop_event=drift_stop),
            name="drift-detector",
        )

        # Daily Telegram digest at DIGEST_HOUR_UTC.
        from app.notifications import digest as _digest

        digest_stop = asyncio.Event()
        digest_task = asyncio.create_task(
            _digest.digest_loop(stop_event=digest_stop),
            name="daily-digest",
        )

        # Daily market-data refresh — IV percentile + earnings dates per
        # watchlist ticker. Phase 6 options runway. Best-effort; failures
        # logged + skipped.
        from app.market_data import derived as _derived

        market_data_stop = asyncio.Event()
        market_data_task = asyncio.create_task(
            _derived.market_data_loop(stop_event=market_data_stop),
            name="market-data-derived",
        )

        # Hourly opportunity generator — runs rule engine over recent
        # predictions, sweeps expired open opportunities. Phase 3.1.
        from app.opportunities import service as _opps_service

        opps_stop = asyncio.Event()

        async def _opps_loop() -> None:
            while True:
                try:
                    await _opps_service.generate_for_predictions()
                    await _opps_service.expire_stale()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.warning("opportunities tick failed: %s", e)
                try:
                    await asyncio.wait_for(opps_stop.wait(), timeout=60 * 60)
                    if opps_stop.is_set():
                        return
                except asyncio.TimeoutError:
                    continue

        opps_task = asyncio.create_task(_opps_loop(), name="opportunities-tick")

        # Submit-queue worker — single-flight FIFO drain. Boot recovery
        # first: any 'running' rows from a crashed prior process flip back
        # to 'pending' so this worker re-picks them.
        from app.queue import service as _qsvc, worker as _qworker

        n_recovered = await _qsvc.reset_stuck_on_boot()
        if n_recovered:
            logger.info("queue: recovered %d stuck rows on boot", n_recovered)

        queue_stop = asyncio.Event()
        queue_task = asyncio.create_task(
            _qworker.worker_loop(stop_event=queue_stop),
            name="queue-worker",
        )

        yield

        # Clean shutdown.
        await _schedule_runner.stop()
        purge_task.cancel()
        accuracy_stop.set()
        accuracy_task.cancel()
        drift_stop.set()
        drift_task.cancel()
        digest_stop.set()
        digest_task.cancel()
        market_data_stop.set()
        market_data_task.cancel()
        opps_stop.set()
        opps_task.cancel()
        queue_stop.set()
        queue_task.cancel()

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
