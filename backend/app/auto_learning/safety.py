"""Safety restrictions for the auto-learning layer.

The learning system is *advisory only*. It may research, evolve, validate and
rank strategies, and it may create promotion *requests* - but it must never:

* enable live trading,
* modify risk limits,
* disable or reset the circuit breaker / kill switch,
* deploy a strategy to production without explicit human approval.

These guarantees are structural (the engine has no code paths that perform those
actions). SafetyGuard provides explicit assertions and a verifiable snapshot so
the guarantees are tested rather than merely documented.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.auto_learning.models import SAFETY_INVARIANTS
from app.models.entities import CircuitBreakerEvent, StrategySettings


class SafetyViolation(RuntimeError):
    pass


class SafetyGuard:
    def __init__(self, db: Session) -> None:
        self.db = db

    # Hard locks - the learning layer can never perform these.
    def assert_can_promote_automatically(self) -> None:
        raise SafetyViolation(
            "Automatic production deployment is forbidden; human approval is required."
        )

    def assert_can_modify_risk_limits(self) -> None:
        raise SafetyViolation("The learning layer must not modify risk limits.")

    def assert_can_touch_circuit_breaker(self) -> None:
        raise SafetyViolation("The learning layer must not disable or reset the circuit breaker.")

    def snapshot(self) -> dict:
        """Read-only snapshot used to verify invariants before/after a cycle."""
        cb = (
            self.db.query(CircuitBreakerEvent)
            .order_by(CircuitBreakerEvent.id.desc())
            .first()
        )
        live = self.db.query(StrategySettings).order_by(StrategySettings.id.asc()).first()
        return {
            "circuit_breaker_event_count": self.db.query(CircuitBreakerEvent).count(),
            "circuit_breaker_latest_id": cb.id if cb else None,
            "live_strategy_enabled": bool(live.is_enabled) if live else None,
            "live_daily_max_loss_pct": float(live.daily_max_loss_pct) if live else None,
        }

    @staticmethod
    def invariants() -> tuple[str, ...]:
        return SAFETY_INVARIANTS

    def verify_unchanged(self, before: dict, after: dict) -> bool:
        """True only if no safety-relevant state changed across a learning run."""
        keys = (
            "circuit_breaker_event_count",
            "live_strategy_enabled",
            "live_daily_max_loss_pct",
        )
        return all(before.get(k) == after.get(k) for k in keys)
