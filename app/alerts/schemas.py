import datetime
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class AlertCreate(BaseModel):
    ticker: str
    alert_type: str
    payload_json: Dict[str, Any]


class AlertResponse(AlertCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime.datetime
    is_read: bool
