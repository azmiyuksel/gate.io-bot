from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, current_user_role, require_admin
from app.core.audit import record_audit
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
def trip(payload: CircuitBreakerActionIn, db: DbSession, user: CurrentUser) -> CircuitBreakerOut:
    breaker = CircuitBreaker(db)
    result = breaker.trip(CircuitBreakerScope.manual, payload.reason, triggered_by=user.email)
    record_audit(db, user.email, "circuit_breaker.trip", payload.reason)
    return result


@router.post("/reset", response_model=CircuitBreakerOut, dependencies=[Depends(require_admin)])
def reset(payload: CircuitBreakerActionIn, db: DbSession, user: CurrentUser) -> CircuitBreakerOut:
    breaker = CircuitBreaker(db)
    result = breaker.reset(triggered_by=user.email, reason=payload.reason)
    record_audit(db, user.email, "circuit_breaker.reset", payload.reason)
    return result
