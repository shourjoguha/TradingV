import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.alerts.schemas import AlertCreate, AlertResponse
from app.alerts.service import fetch_unread_and_mark_read, save_alert
from app.core.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(tags=["alerts"])


@router.post("/webhook")
async def receive_webhook(
    alert: AlertCreate,
    background_tasks: BackgroundTasks,
    _api_key: str = Depends(verify_api_key),
):
    background_tasks.add_task(save_alert, alert)
    return {"status": "ok"}


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(_api_key: str = Depends(verify_api_key)):
    try:
        return await fetch_unread_and_mark_read()
    except Exception as e:
        logger.error("fetch_alerts failed: %s", e)
        raise HTTPException(status_code=500, detail="Fetch error")
