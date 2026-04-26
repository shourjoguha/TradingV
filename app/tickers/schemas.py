import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

AssetClass = Literal["stock", "etf", "crypto"]
TickerSource = Literal[
    "alert", "manual", "analysis", "peer_sync", "watchlist", "labels"
]


class TickerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    asset_class: AssetClass
    source: TickerSource
    first_seen: datetime.datetime
    last_seen: datetime.datetime
    notes: Optional[str] = None


class TickerCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=50)
    asset_class: Optional[AssetClass] = None
    notes: Optional[str] = None


class TickerBulkCreate(BaseModel):
    tickers: List[TickerCreate]


class TickerPatch(BaseModel):
    asset_class: Optional[AssetClass] = None
    notes: Optional[str] = None
