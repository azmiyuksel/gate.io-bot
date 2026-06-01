from fastapi import APIRouter, Depends

from app.api.deps import DbSession, current_user_role, require_admin
from app.models.enums import CircuitBreakerScope
from app.schemas.circuit_breaker import (
    CircuitBreakerActionIn,
    CircuitBreakerOut,
    CircuitBreakerStatusOut,
)
from app.services.risk.circuit_breaker import CircuitBreaker

router = APIRouter(
    prefix="/circuit-breaker", tags=["circuit-breaker"], dependencies=[Depends(current_user_role)]
)


@router.get("", response_model=CircuitBreakerStatusOut)
def status(db: DbSession) -> CircuitBreakerStatusOut:
    breaker = CircuitBreaker(db)
    return CircuitBreakerStatusOut(is_tripped=breaker.is_tripped(), current=breaker.current())


@router.post("/trip", response_model=CircuitBreakerOut, dependencies=[Depends(require_admin)])
def trip(payload: CircuitBreakerActionIn, db: DbSession) -> CircuitBreakerOut:
    breaker = CircuitBreaker(db)
    return breaker.trip(CircuitBreakerScope.manual, payload.reason, triggered_by="user")


@router.post("/reset", response_model=CircuitBreakerOut, dependencies=[Depends(require_admin)])
def reset(payload: CircuitBreakerActionIn, db: DbSession) -> CircuitBreakerOut:
    breaker = CircuitBreaker(db)
    return breaker.reset(triggered_by="user", reason=payload.reason)
