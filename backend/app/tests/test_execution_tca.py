"""Tests for implementation-shortfall transaction-cost analysis."""
from app.execution_quality.tca import (
    aggregate_implementation_shortfall,
    implementation_shortfall,
)


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
