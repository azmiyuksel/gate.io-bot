"""Tests for implementation-shortfall transaction-cost analysis."""
from app.execution_quality.tca import (
    aggregate_implementation_shortfall,
    benchmark_slippage_bps,
    implementation_shortfall,
    markout_bps,
    twap,
    vwap,
)


def test_markout_detects_adverse_selection():
    # Bought at 100, price fell to 99 afterwards -> adverse (negative markout).
    assert markout_bps("buy", 100.0, 99.0) == -100.0
    # Bought at 100, price rose to 101 -> favourable.
    assert markout_bps("buy", 100.0, 101.0) == 100.0
    # Sold at 100, price rose to 101 afterwards -> adverse for a sell.
    assert markout_bps("sell", 100.0, 101.0) == -100.0


def test_vwap_weights_by_volume():
    # Most volume traded at 100; a high-volume print pulls VWAP toward it.
    assert abs(vwap([100.0, 110.0], [9.0, 1.0]) - 101.0) < 1e-9
    # No volume -> simple mean.
    assert vwap([100.0, 110.0], [0.0, 0.0]) == 105.0


def test_twap_simple_mean():
    assert twap([100.0, 102.0, 104.0]) == 102.0


def test_benchmark_slippage_direction():
    # Buy above VWAP is a cost; sell above VWAP beats the benchmark.
    assert benchmark_slippage_bps("buy", 101.0, 100.0) == 100.0
    assert benchmark_slippage_bps("sell", 101.0, 100.0) == -100.0


def test_buy_paying_above_decision_is_a_cost():
    # Decision 100, filled 1 unit at 100.5 with 0.1 fee. Notional 100.
    out = implementation_shortfall("buy", 100.0, 100.5, 1.0, 1.0, fee=0.1)
    # Price cost 0.5 + fee 0.1 = 0.6 over 100 notional = 60 bps.
    assert abs(out["is_bps"] - 60.0) < 1e-9
    assert abs(out["execution_cost_bps"] - 50.0) < 1e-9
    assert abs(out["fee_bps"] - 10.0) < 1e-9
    assert out["unfilled_ratio"] == 0.0


def test_buy_price_improvement_is_negative_cost():
    out = implementation_shortfall("buy", 100.0, 99.5, 1.0, 1.0, fee=0.0)
    assert out["execution_cost_bps"] < 0  # filled below decision price


def test_sell_receiving_below_decision_is_a_cost():
    # Sell: receiving less than the decision price is adverse.
    out = implementation_shortfall("sell", 100.0, 99.0, 1.0, 1.0, fee=0.0)
    assert abs(out["execution_cost_bps"] - 100.0) < 1e-9  # 1.0/100 * 1e4


def test_unfilled_quantity_reported():
    out = implementation_shortfall("buy", 100.0, 100.0, 0.4, 1.0, fee=0.0)
    assert abs(out["unfilled_ratio"] - 0.6) < 1e-9


def test_aggregate_averages_components():
    records = [
        implementation_shortfall("buy", 100.0, 100.5, 1.0, 1.0, fee=0.1),
        implementation_shortfall("buy", 100.0, 100.0, 1.0, 1.0, fee=0.0),
    ]
    agg = aggregate_implementation_shortfall(records)
    assert agg["orders"] == 2
    assert abs(agg["avg_is_bps"] - 30.0) < 1e-9  # (60 + 0)/2


def test_aggregate_empty():
    agg = aggregate_implementation_shortfall([])
    assert agg["orders"] == 0
    assert agg["avg_is_bps"] == 0.0
