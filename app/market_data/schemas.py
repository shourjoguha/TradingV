import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class BarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    interval: str
    ts: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: Optional[float] = None
    provider: str


class OhlcvResponse(BaseModel):
    symbol: str
    interval: str
    count: int
    bars: List[BarResponse]
