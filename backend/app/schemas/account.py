from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class AccountSnapshotOut(BaseModel):
    id: int
    exchange: str
    quote_currency: str
    cash_balance: Decimal
    available_balance: Decimal
    locked_balance: Decimal
    positions_value: Decimal
    total_equity: Decimal
    balances: dict
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class EquityOut(BaseModel):
    total_equity: Decimal
    peak_equity: Decimal
    drawdown_pct: Decimal
    source: str
