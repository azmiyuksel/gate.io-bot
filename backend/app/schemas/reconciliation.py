from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ReconciliationLogOut(BaseModel):
    id: int
    order_id: int | None
    exchange_order_id: str | None
    symbol: str
    action: str
    previous_status: str | None
    new_status: str | None
    filled_quantity: Decimal
    detail: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ReconciliationRunOut(BaseModel):
    reconciled: int
    changed: int
    logs: list[ReconciliationLogOut]
