"""Transaction-cost analysis: implementation shortfall (Perold).

Implementation shortfall measures the all-in cost of execution against the
DECISION price (the price when the signal fired), capturing adverse price
movement, fees and unfilled quantity in a single basis-point figure — the
standard institutional TCA benchmark, which the module previously lacked.
"""
from __future__ import annotations


def implementation_shortfall(
    side: str,
    decision_price: float,
    fill_price: float,
    fill_quantity: float,
    expected_quantity: float,
    fee: float = 0.0,
) -> dict:
    """All-in execution cost vs the decision price, in basis points.

    Positive = worse than the decision price (a cost); negative = price
    improvement. Decomposed into the price (execution) component and the fee
    component, plus the unfilled ratio (opportunity-cost exposure).
    """
    decision_notional = expected_quantity * decision_price
    if decision_notional <= 0:
        return {
            "is_bps": 0.0,
            "execution_cost_bps": 0.0,
            "fee_bps": 0.0,
            "unfilled_ratio": 0.0,
        }
    direction = 1.0 if side.lower() == "buy" else -1.0
    # Buy: paying above the decision price is adverse; sell: receiving below is.
    execution_cost = fill_quantity * (fill_price - decision_price) * direction
    total_cost = execution_cost + fee
    unfilled = max(0.0, (expected_quantity - fill_quantity) / expected_quantity)
    return {
        "is_bps": total_cost / decision_notional * 1e4,
        "execution_cost_bps": execution_cost / decision_notional * 1e4,
        "fee_bps": fee / decision_notional * 1e4,
        "unfilled_ratio": unfilled,
    }


def aggregate_implementation_shortfall(records: list[dict]) -> dict:
    """Average the per-order implementation-shortfall components."""
    if not records:
        return {
            "avg_is_bps": 0.0,
            "avg_execution_cost_bps": 0.0,
            "avg_fee_bps": 0.0,
            "avg_unfilled_ratio": 0.0,
            "orders": 0,
        }
    n = len(records)
    return {
        "avg_is_bps": sum(r["is_bps"] for r in records) / n,
        "avg_execution_cost_bps": sum(r["execution_cost_bps"] for r in records) / n,
        "avg_fee_bps": sum(r["fee_bps"] for r in records) / n,
        "avg_unfilled_ratio": sum(r["unfilled_ratio"] for r in records) / n,
        "orders": n,
    }
