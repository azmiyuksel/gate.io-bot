from datetime import UTC, datetime
from decimal import Decimal

from app.models.entities import Trade
from app.models.enums import CircuitBreakerScope, CircuitBreakerState, OrderSide
from app.repositories.trading import StrategySettingsRepository
from app.services.risk.circuit_breaker import CircuitBreaker


def test_breaker_starts_armed(db_session) -> None:
    breaker = CircuitBreaker(db_session)
    assert breaker.is_tripped() is False
    assert breaker.current() is None


def test_manual_trip_and_reset_disable_strategy(db_session) -> None:
    settings = StrategySettingsRepository(db_session).current()
    settings.is_enabled = True
    db_session.commit()

    breaker = CircuitBreaker(db_session)
    event = breaker.trip(CircuitBreakerScope.manual, "kill", triggered_by="user")
    assert event.state == CircuitBreakerState.tripped
    assert breaker.is_tripped() is True
    # Tripping halts the strategy.
    assert StrategySettingsRepository(db_session).current().is_enabled is False

    breaker.reset(triggered_by="user", reason="all clear")
    assert breaker.is_tripped() is False


def test_daily_loss_limit_trips_breaker(db_session) -> None:
    # Default daily_max_loss_pct is 0.02 -> on 10k equity the limit is -200.
    settings = StrategySettingsRepository(db_session).current()
    settings.is_enabled = True
    db_session.add(
        Trade(
            symbol="BTC_USDT",
            side=OrderSide.sell,
            price=Decimal("100"),
            quantity=Decimal("1"),
            realized_pnl=Decimal("-500"),
            traded_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    breaker = CircuitBreaker(db_session)
    result = breaker.evaluate(Decimal("10000"))
    assert result.tripped is True
    assert result.scope == CircuitBreakerScope.daily_loss

    assert breaker.check_and_trip(Decimal("10000")) is True
    assert breaker.is_tripped() is True


def test_drawdown_limit_trips_breaker(db_session) -> None:
    StrategySettingsRepository(db_session).current()
    breaker = CircuitBreaker(db_session)
    # max_account_drawdown_pct default is 0.15.
    result = breaker.evaluate(Decimal("10000"), drawdown_pct=Decimal("0.20"))
    assert result.tripped is True
    assert result.scope == CircuitBreakerScope.drawdown
