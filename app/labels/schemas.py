from __future__ import annotations

import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class LabelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    key: str
    value: Any
    created_at: datetime.datetime
    updated_at: datetime.datetime


class LabelUpsert(BaseModel):
    """PUT body for a single (symbol, key) → value upsert."""

    value: Any = Field(..., description="Any JSON-serialisable value.")


class LabelsBulkUpsert(BaseModel):
    """PUT body to upsert many keys in one call. Each key replaces its
    existing value; keys absent here are NOT removed."""

    labels: Dict[str, Any] = Field(..., min_length=1)


class LabelsListResponse(BaseModel):
    symbol: str
    labels: List[LabelRead]
