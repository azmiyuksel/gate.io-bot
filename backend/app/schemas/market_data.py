from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CandleOut(BaseModel):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    class Config:
        from_attributes = True


class IngestionResultOut(BaseModel):
    inserted: dict[str, int]


class LatestPriceOut(BaseModel):
    prices: dict[str, float]
