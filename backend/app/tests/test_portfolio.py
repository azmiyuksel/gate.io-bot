from decimal import Decimal

from app.portfolio.allocator import CapitalAllocator
from app.portfolio.performance import PerformanceCalculator
from app.portfolio.risk_model import PortfolioRiskModel


def test_performance_calculator_metrics() -> None:
    # 1. Test Win Rate
    class MockTrade:
        def __init__(self, pnl: float) -> None:
            self.realized_pnl = pnl

    trades = [MockTrade(10.0), MockTrade(-5.0), MockTrade(20.0), MockTrade(0.0)]
    win_rate = PerformanceCalculator.calculate_win_rate(trades)
    assert win_rate == 0.5  # 2 wins out of 4 trades

    # 2. Test Profit Factor
    profit_factor = PerformanceCalculator.calculate_profit_factor(trades)
    assert profit_factor == 30.0 / 5.0  # Gross Profit: 30, Gross Loss: 5

    # 3. Test Drawdown
    equity_curve = [10000, 10500, 10200, 10800, 9900]
    drawdown = PerformanceCalculator.calculate_drawdown(equity_curve)
    assert drawdown == (10800 - 9900) / 10800  # peak is 10800, trough is 9900

    # 4. Test Stability Score
    stability = PerformanceCalculator.calculate_stability_score([100, 101, 102, 103, 104])
    assert stability == 1.0  # Perfectly linear


def test_capital_allocator_formula() -> None:
    # Allocation score = 0.4 * strategy_score + 0.3 * risk_adjusted_return + 0.2 * inverse_correlation_penalty + 0.1 * stability_score
    strategy_score = Decimal("0.8")
    risk_adjusted = Decimal("0.7")
    inv_corr = Decimal("0.9")
    stability = Decimal("0.85")

    expected = (
        Decimal("0.40") * strategy_score +
        Decimal("0.30") * risk_adjusted +
        Decimal("0.20") * inv_corr +
        Decimal("0.10") * stability
    )

    actual = CapitalAllocator.calculate_allocation_score(
        strategy_score,
        risk_adjusted,
        inv_corr,
        stability
    )
    assert actual == expected


def test_risk_model_position_sizing() -> None:
    equity = Decimal("10000")
    price = Decimal("100")
    atr = Decimal("2")
    risk_pct = Decimal("0.01")  # 1% risk
    atr_multiplier = Decimal("2.0")

    # expected SL distance = 2 * 2 = 4
    # expected risk amount = 10000 * 0.01 = 100
    # expected quantity = 100 / 4 = 25
    # expected SL price = 100 - 4 = 96

    qty, sl_dist, sl_price = PortfolioRiskModel.calculate_position_size(
        equity, price, atr, risk_pct, atr_multiplier
    )

    assert sl_dist == Decimal("4")
    assert qty == Decimal("25")
    assert sl_price == Decimal("96")


def test_correlations_endpoint_reports_data_availability(db_session):
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.api.v1.portfolio import get_correlations
    from app.core.config import get_settings
    from app.models.entities import HistoricalCandle

    # No candles yet -> must not present fake data.
    empty = get_correlations(db_session)
    assert empty["data_available"] is False
    assert empty["symbols"] == []

    tf = get_settings().market_data_interval
    base = datetime(2024, 1, 1, tzinfo=UTC)
    for sym, drift in (("BTC_USDT", "1.0"), ("ETH_USDT", "0.5")):
        for i in range(15):
            price = Decimal("100") + Decimal(str(i)) * Decimal(drift)
            db_session.add(HistoricalCandle(
                symbol=sym, timeframe=tf, timestamp=base + timedelta(hours=i),
                open=price, high=price, low=price, close=price, volume=Decimal("1000"),
                source="test",
            ))
    db_session.commit()

    result = get_correlations(db_session)
    assert result["data_available"] is True
    assert "BTC_USDT" in result["symbols"] and "ETH_USDT" in result["symbols"]
    # Self-correlation is 1.0 on the diagonal.
    assert round(result["matrix"]["BTC_USDT"]["BTC_USDT"], 6) == 1.0
