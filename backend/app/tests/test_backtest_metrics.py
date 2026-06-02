import pandas as pd

from app.backtest.metrics import compute_metrics, monte_carlo
from app.backtest.models import BacktestTradeResult


def test_compute_metrics_handles_winning_and_losing_trades() -> None:
    equity = [
        {"timestamp": "2024-01-01T00:00:00+00:00", "equity": 10000},
        {"timestamp": "2024-01-01T01:00:00+00:00", "equity": 10100},
        {"timestamp": "2024-01-01T02:00:00+00:00", "equity": 10050},
    ]
    trades = [
        BacktestTradeResult("BTC_USDT", "long", pd.Timestamp.utcnow(), pd.Timestamp.utcnow(), 100, 110, 1, 0, 10, 0.1, "take_profit"),
        BacktestTradeResult("BTC_USDT", "long", pd.Timestamp.utcnow(), pd.Timestamp.utcnow(), 100, 95, 1, 0, -5, -0.05, "stop_loss"),
    ]
    metrics = compute_metrics(equity, trades)
    assert metrics["total_trades"] == 2
    assert metrics["winning_trades"] == 1
    assert metrics["profit_factor"] == 2


def test_monte_carlo_returns_ruin_probability() -> None:
    trades = [
        BacktestTradeResult("BTC_USDT", "long", pd.Timestamp.utcnow(), pd.Timestamp.utcnow(), 100, 110, 1, 0, 10, 0.1, "take_profit")
    ]
    result = monte_carlo(trades, 1000, scenarios=1000)
    assert result["scenarios"] == 1000
    assert 0 <= result["ruin_probability"] <= 1


def test_monte_carlo_compounds_returns() -> None:
    ts = pd.Timestamp.utcnow()
    # Three +10% trades on equity-before-trade (1000->1100->1210->1331):
    # pnls 100, 110, 121 each reconstruct to a 0.1 equity-fraction return.
    trades = [
        BacktestTradeResult("BTC_USDT", "long", ts, ts, 100, 110, 1, 0, 100, 0.1, "take_profit"),
        BacktestTradeResult("BTC_USDT", "long", ts, ts, 100, 110, 1, 0, 110, 0.1, "take_profit"),
        BacktestTradeResult("BTC_USDT", "long", ts, ts, 100, 110, 1, 0, 121, 0.1, "take_profit"),
    ]
    result = monte_carlo(trades, 1000, scenarios=100)
    # Compounding three 10% returns => 1.1**3 - 1 = 0.331, strictly above the
    # additive sum of 0.30. Every scenario is identical (one unique return).
    assert abs(result["median_return"] - 0.331) < 1e-9
    assert result["median_return"] > 0.30
    assert result["ruin_probability"] == 0
