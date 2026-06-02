"""Tests for trade-economics edge metrics and benchmark comparison."""
from app.services.analytics.economics import benchmark_comparison, trade_economics


def test_edge_positive_when_expectancy_and_winrate_clear_breakeven():
    # 2:1 payoff, 50% win rate: break-even is 1/(2+1)=0.333, so 0.5 > 0.333 => edge.
    pnls = [20.0, 20.0, -10.0, -10.0]
    e = trade_economics(pnls)
    assert e["win_rate"] == 0.5
    assert e["payoff_ratio"] == 2.0
    assert abs(e["break_even_win_rate"] - (10.0 / 30.0)) < 1e-9
    assert e["edge"] > 0
    assert e["expectancy"] == 5.0
    assert e["has_edge"] is True


def test_no_edge_when_expectancy_negative():
    # 1:2 payoff, 50% win rate: loses money -> no edge.
    pnls = [10.0, 10.0, -20.0, -20.0]
    e = trade_economics(pnls)
    assert e["expectancy"] == -5.0
    assert e["edge"] < 0
    assert e["has_edge"] is False


def test_expectancy_in_r_multiple():
    pnls = [20.0, -10.0]  # expectancy 5, avg_loss 10 -> 0.5R
    e = trade_economics(pnls)
    assert abs(e["expectancy_r"] - 0.5) < 1e-9


def test_economics_empty():
    e = trade_economics([])
    assert e["trades"] == 0
    assert e["has_edge"] is False


def test_benchmark_excess_return():
    # Strategy +5% while BTC went 100->110 (+10%) -> underperforms (excess -5%).
    out = benchmark_comparison(0.05, [100.0, 110.0])
    assert abs(out["benchmark_return"] - 0.10) < 1e-9
    assert abs(out["excess_return"] - (-0.05)) < 1e-9
    assert out["outperforms"] is False


def test_benchmark_outperforms():
    out = benchmark_comparison(0.20, [100.0, 110.0])
    assert out["outperforms"] is True
