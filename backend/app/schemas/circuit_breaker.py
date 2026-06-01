from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CircuitBreakerOut(BaseModel):
    id: int
    state: str
    scope: str
    reason: str
    triggered_value: Decimal | None
    threshold_value: Decimal | None
    triggered_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class CircuitBreakerStatusOut(BaseModel):
    is_tripped: bool
    current: CircuitBreakerOut | None


class CircuitBreakerActionIn(BaseModel):
    reason: str = "manual"
