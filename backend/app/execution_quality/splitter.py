"""Order splitting for large entries (TWAP child orders).

A single market order on a large notional slippes badly on less-liquid
altcoins (WIF/BONK/PEPE etc.). Splitting the entry into N time-sliced child
orders reduces market impact: each child is a smaller market order spaced
~`delay_seconds` apart, approximating a TWAP execution. The total quantity is
preserved; partial fills on an earlier child do not abort the rest (the
position is persisted at the aggregate filled quantity after all children).

This is a best-effort impact reducer, not a full TWAP/VWAP engine — it does not
track volume curves or adjust for intrabar volatility. It keeps the order path
simple while cutting the worst-case slippage on fat orders.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class SplitDecision:
    """Result of deciding whether and how to split an entry order.

    ``should_split`` is False when the notional is below the threshold (a single
    order is fine). When True, `child_quantities` lists the per-child base
    quantities to submit ~`delay_seconds` apart.
    """
    should_split: bool
    child_quantities: list
    delay_seconds: float


def plan_split(
    base_quantity, notional: float, equity: float, *, threshold_pct: float, child_count: int,
) -> SplitDecision:
    """Decide whether to split and how.

    Splits when the entry notional exceeds `threshold_pct` of equity. The
    quantity is divided into `child_count` roughly-equal parts (the last child
    absorbs the rounding remainder so the total is exact).
    """
    if threshold_pct <= 0 or child_count <= 1:
        return SplitDecision(False, [base_quantity], 0.0)
    threshold = float(equity) * float(threshold_pct)
    if float(notional) <= threshold:
        return SplitDecision(False, [base_quantity], 0.0)
    # Equal split with the last child absorbing the remainder.
    from decimal import Decimal

    q = base_quantity if isinstance(base_quantity, Decimal) else Decimal(str(base_quantity))
    child_count = max(int(child_count), 2)
    per = q // child_count
    children = [per] * child_count
    children[-1] = q - per * (child_count - 1)  # remainder into the last child
    # Drop any zero-sized children (can happen when qty < child_count).
    children = [c for c in children if c > 0]
    if len(children) <= 1:
        return SplitDecision(False, [base_quantity], 0.0)
    return SplitDecision(True, children, 2.0)


async def execute_split(
    submit_child, decision: SplitDecision,
) -> list:
    """Execute a split decision by calling `submit_child(quantity)` for each
    child, ~`delay_seconds` apart. Returns the list of per-child responses.

    `submit_child` is an awaitable taking the child base quantity and returning
    the exchange response dict. A failure on one child does NOT abort the rest —
    the caller persists whatever filled.
    """
    responses = []
    for i, qty in enumerate(decision.child_quantities):
        if i > 0 and decision.delay_seconds > 0:
            await asyncio.sleep(decision.delay_seconds)
        try:
            resp = await submit_child(qty)
            responses.append(resp)
        except Exception:
            # A failed child is logged by the caller; continue with the rest so
            # a transient error on child 2/3 does not leave the entry half-done.
            responses.append(None)
    return responses
