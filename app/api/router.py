from fastapi import APIRouter

from app.alerts.routes import router as alerts_router
from app.analysis.routes import router as analysis_router
from app.kronos.routes import router as kronos_router
from app.market_data.routes import router as market_data_router
from app.sync.routes import router as sync_router
from app.tickers.routes import router as tickers_router
from app.labels.routes import import_router as labels_import_router, router as labels_router
from app.predictions.routes import router as predictions_router
from app.schedule.routes import router as schedule_router
from app.watchlist.routes import router as watchlist_router

api_router = APIRouter()
# Legacy (unversioned) — keep for existing TradingView webhook URL.
api_router.include_router(alerts_router)

# Versioned v1 surface.
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(tickers_router)
v1_router.include_router(market_data_router)
v1_router.include_router(kronos_router)
v1_router.include_router(analysis_router)
v1_router.include_router(sync_router)
v1_router.include_router(watchlist_router)
v1_router.include_router(schedule_router)
v1_router.include_router(predictions_router)
v1_router.include_router(labels_router)
v1_router.include_router(labels_import_router)
api_router.include_router(v1_router)
