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
from app.accuracy.routes import router as accuracy_router
from app.opportunities.routes import router as opportunities_router
from app.trades.routes import router as trades_router
from app.queue.routes import router as queue_router
from app.macro.routes import router as macro_router
from app.boards.routes import router as boards_router
from app.hypotheses.routes import router as hypotheses_router
from app.views.routes import router as views_router
from app.research.routes import router as research_router
from app.tv_context.routes import router as tv_context_router
from app.the_street.routes import router as the_street_router
from app.vault.routes import router as vault_router
from app.admin.routes import router as admin_router
from app.earnings.routes import router as earnings_router
from app.ticker_review.routes import router as ticker_review_router

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
v1_router.include_router(accuracy_router)
v1_router.include_router(opportunities_router)
v1_router.include_router(trades_router)
v1_router.include_router(queue_router)
v1_router.include_router(macro_router)
v1_router.include_router(boards_router)
v1_router.include_router(hypotheses_router)
v1_router.include_router(views_router)
v1_router.include_router(research_router)
v1_router.include_router(tv_context_router)
v1_router.include_router(the_street_router)
v1_router.include_router(vault_router)
v1_router.include_router(admin_router)
v1_router.include_router(earnings_router)
v1_router.include_router(ticker_review_router)
api_router.include_router(v1_router)
