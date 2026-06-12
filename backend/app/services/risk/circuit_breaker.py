from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import CircuitBreakerEvent, SystemLog
from app.models.enums import CircuitBreakerScope, CircuitBreakerState, LogLevel
from app.repositories.trading import StrategySettingsRepository, TradeRepository


@dataclass(frozen=True)
class BreakerCheck:
    tripped: bool
    scope: CircuitBreakerScope | None = None
    reason: str = "ok"


class CircuitBreaker:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.trades = TradeRepository(db)
        self.settings_repo = StrategySettingsRepository(db)
        self.config = get_settings()

    def current(self) -> CircuitBreakerEvent | None:
        return (
            self.db.query(CircuitBreakerEvent)
            .order_by(CircuitBreakerEvent.created_at.desc(), CircuitBreakerEvent.id.desc())
            .first()
        )

    def is_tripped(self) -> bool:
        event = self.current()
        return event is not None and event.state == CircuitBreakerState.tripped

    def evaluate(self, equity: Decimal, drawdown_pct: Decimal | None = None) -> BreakerCheck:
        """Check limits against current PnL/drawdown without mutating state."""
        settings = self.settings_repo.current()

        daily_limit = -(equity * settings.daily_max_loss_pct)
        if self.trades.daily_pnl() <= daily_limit:
            return BreakerCheck(True, CircuitBreakerScope.daily_loss,
                                f"daily PnL {self.trades.daily_pnl()} <= limit {daily_limit}")

        weekly_limit = -(equity * settings.weekly_max_loss_pct)
        if self.trades.weekly_pnl() <= weekly_limit:
            return BreakerCheck(True, CircuitBreakerScope.weekly_loss,
                                f"weekly PnL {self.trades.weekly_pnl()} <= limit {weekly_limit}")

        if drawdown_pct is not None:
            max_dd = Decimal(str(self.config.max_account_drawdown_pct))
            if drawdown_pct >= max_dd:
                return BreakerCheck(True, CircuitBreakerScope.drawdown,
                                    f"drawdown {drawdown_pct:.4f} >= limit {max_dd}")

        return BreakerCheck(False)

    def check_and_trip(self, equity: Decimal, drawdown_pct: Decimal | None = None) -> bool:
        """Evaluate limits and trip if breached. Returns True if trading is halted."""
        if self.is_tripped():
            return True
        result = self.evaluate(equity, drawdown_pct)
        if result.tripped:
            self.trip(result.scope, result.reason, triggered_by="system",
                      triggered_value=equity)
            return True
        return False

    def trip(
        self,
        scope: CircuitBreakerScope | None,
        reason: str,
        triggered_by: str = "system",
        triggered_value: Decimal | None = None,
        threshold_value: Decimal | None = None,
    ) -> CircuitBreakerEvent:
        event = CircuitBreakerEvent(
            state=CircuitBreakerState.tripped,
            scope=scope or CircuitBreakerScope.manual,
            reason=reason,
            triggered_value=triggered_value,
            threshold_value=threshold_value,
            triggered_by=triggered_by,
        )
        self.db.add(event)
        # Halt the strategy so the scheduler stops opening new positions.
        settings = self.settings_repo.current()
        settings.is_enabled = False
        self.db.add(
            SystemLog(level=LogLevel.error, source="circuit_breaker",
                      message=f"TRIPPED ({event.scope}): {reason}")
        )
        self.db.commit()
        self.db.refresh(event)
        return event

    def reset(self, triggered_by: str = "system", reason: str = "manual reset") -> CircuitBreakerEvent:
        # Before resetting, check if enough time has passed since the last reset
        # to prevent immediate re-enabling of the strategy.
        last_event = self.current()
        if last_event and last_event.state == CircuitBreakerState.tripped:
            # Find the last reset event (armed state)
            last_reset = (
                self.db.query(CircuitBreakerEvent)
                .filter(CircuitBreakerEvent.state == CircuitBreakerState.armed)
                .order_by(CircuitBreakerEvent.created_at.desc(), CircuitBreakerEvent.id.desc())
                .first()
            )
            if last_reset:
                time_since_reset = datetime.now(UTC) - last_reset.created_at
                # Require a minimum cooldown of 1 hour before allowing re-enable
                from datetime import timedelta
                if time_since_reset < timedelta(hours=1):
                    raise RuntimeError(
                        f"Circuit breaker reset cooldown active. "
                        f"Reset {time_since_reset} ago, minimum 1 hour required."
                    )
        
        event = CircuitBreakerEvent(
            state=CircuitBreakerState.armed,
            scope=CircuitBreakerScope.manual,
            reason=reason,
            triggered_by=triggered_by,
        )
        self.db.add(event)
        self.db.add(
            SystemLog(level=LogLevel.warning, source="circuit_breaker",
                      message=f"RESET by {triggered_by}: {reason}")
        )
        self.db.commit()
        self.db.refresh(event)
        return event
