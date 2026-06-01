from decimal import Decimal

from app.services.strategy.indicators import ema, rsi


def test_ema_returns_value_with_enough_history() -> None:
    values = [Decimal(i) for i in range(1, 31)]
    assert ema(values, 20) is not None


def test_rsi_bounds() -> None:
    values = [Decimal("100"), Decimal("99"), Decimal("98"), Decimal("97"), Decimal("98")] * 4
    result = rsi(values, 14)
    assert result is not None
    assert Decimal("0") <= result <= Decimal("100")
