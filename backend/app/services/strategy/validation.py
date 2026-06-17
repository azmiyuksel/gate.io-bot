"""Go-live gate: has the live strategy passed out-of-sample validation?

Before a strategy trades real money it should have demonstrated robustness on
unseen data. This checks for a COMPLETED walk-forward run for the live strategy
on the live timeframe whose deployment decision passed the validator's checks
(robustness/consistency/WFE/Sharpe/drawdown/overfit) and is recent enough.

The gate is intentionally per strategy+timeframe (not per symbol): walk-forward
validates the STRATEGY's edge, typically on a representative pair, not every
tradable symbol.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.entities import WalkForwardRun
from app.models.enums import WalkForwardStatus


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str
    run_id: int | None = None


def latest_completed_run(db: Session, strategy_name: str, timeframe: str) -> WalkForwardRun | None:
    return (
        db.query(WalkForwardRun)
        .filter(
            WalkForwardRun.strategy_name == strategy_name,
            WalkForwardRun.timeframe == timeframe,
            WalkForwardRun.status == WalkForwardStatus.completed,
        )
        .order_by(WalkForwardRun.completed_at.desc(), WalkForwardRun.id.desc())
        .first()
    )


def live_strategy_validated(
    db: Session, strategy_name: str, timeframe: str, max_age_days: int
) -> ValidationResult:
    """Whether the live strategy is cleared to open new trades."""
    run = latest_completed_run(db, strategy_name, timeframe)
    if run is None:
        return ValidationResult(
            False, f"no completed walk-forward for {strategy_name} @ {timeframe}"
        )
    decision = run.deployment_decision or {}
    if not decision.get("approved"):
        return ValidationResult(
            False, f"walk-forward run #{run.id} did not pass validation checks", run.id
        )
    completed = run.completed_at
    if completed is None:
        return ValidationResult(False, f"walk-forward run #{run.id} has no completion time", run.id)
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=UTC)
    age_days = (datetime.now(UTC) - completed).days
    if max_age_days > 0 and age_days > max_age_days:
        return ValidationResult(
            False,
            f"walk-forward run #{run.id} is stale ({age_days}d old > {max_age_days}d limit)",
            run.id,
        )
    return ValidationResult(True, f"validated by walk-forward run #{run.id}", run.id)
