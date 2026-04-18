import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List
import datetime

from fastapi import FastAPI, Depends, HTTPException, Security, BackgroundTasks
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy import String, DateTime, Boolean, JSON, func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

from config import SETTINGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_url = SETTINGS.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
engine = create_async_engine(db_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(50))
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    alert_type: Mapped[str] = mapped_column(String(50))
    payload_json: Mapped[dict] = mapped_column(JSON)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

class AlertCreate(BaseModel):
    ticker: str
    alert_type: str
    payload_json: Dict[str, Any]

class AlertResponse(AlertCreate):
    id: int
    timestamp: datetime.datetime
    is_read: bool

api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if api_key != SETTINGS.API_KEY:
        raise HTTPException(status_code=403, detail="Bad key")
    return api_key

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield
    except Exception as e:
        logger.error(f"DB error: {e}")
        raise

app = FastAPI(lifespan=lifespan)

async def save_alert_task(alert_data: AlertCreate):
    try:
        async with SessionLocal() as session:
            db_alert = Alert(
                ticker=alert_data.ticker,
                alert_type=alert_data.alert_type,
                payload_json=alert_data.payload_json
            )
            session.add(db_alert)
            await session.commit()
    except Exception as e:
        logger.error(f"Save error: {e}")

@app.post("/webhook")
async def receive_webhook(
    alert: AlertCreate,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    background_tasks.add_task(save_alert_task, alert)
    return {"status": "ok"}

@app.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(api_key: str = Depends(verify_api_key)):
    try:
        async with SessionLocal() as session:
            result = await session.execute(select(Alert).where(Alert.is_read == False))
            alerts = result.scalars().all()
            
            if alerts:
                for a in alerts:
                    a.is_read = True
                await session.commit()
                
            return alerts
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        raise HTTPException(status_code=500, detail="Fetch error")