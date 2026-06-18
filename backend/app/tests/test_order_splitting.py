"""Tests for order splitting (TWAP child orders) and adaptive limit entry."""
from decimal import Decimal

import pytest

from app.execution_quality.splitter import SplitDecision, execute_split, plan_split


def test_plan_split_no_split_below_threshold():
    # Notional 100 on equity 10000 = 1% < 3% threshold -> no split.
    decision = plan_split(
        Decimal("1"), notional=100.0, equity=10000.0,
        threshold_pct=0.03, child_count=3,
    )
    assert decision.should_split is False
    assert decision.child_quantities == [Decimal("1")]


def test_plan_split_above_threshold_splits_into_children():
    # Notional 500 on equity 10000 = 5% > 3% threshold -> split into 3.
    decision = plan_split(
        Decimal("30"), notional=500.0, equity=10000.0,
        threshold_pct=0.03, child_count=3,
    )
    assert decision.should_split is True
    assert len(decision.child_quantities) == 3
    # Total preserved; last child absorbs the rounding remainder.
    assert sum(decision.child_quantities) == Decimal("30")


def test_plan_split_zero_threshold_disables():
    decision = plan_split(
        Decimal("30"), notional=9999.0, equity=10000.0,
        threshold_pct=0.0, child_count=3,
    )
    assert decision.should_split is False


def test_plan_split_single_child_count_disables():
    decision = plan_split(
        Decimal("30"), notional=500.0, equity=10000.0,
        threshold_pct=0.03, child_count=1,
    )
    assert decision.should_split is False


@pytest.mark.asyncio
async def test_execute_split_calls_submit_for_each_child(monkeypatch):
    # execute_split should call submit_child once per child with a delay between.
    delays = []

    async def fake_sleep(d):
        delays.append(d)

    monkeypatch.setattr("app.execution_quality.splitter.asyncio.sleep", fake_sleep)
    calls = []

    async def submit_child(qty):
        calls.append(qty)
        return {"id": str(qty), "avg_deal_price": "100", "filled_total": str(qty * 100)}

    decision = SplitDecision(True, [Decimal("10"), Decimal("10"), Decimal("10")], 2.0)
    responses = await execute_split(submit_child, decision)
    assert len(calls) == 3
    assert len(responses) == 3
    # A delay is inserted before child 2 and child 3 (not before child 1).
    assert len(delays) == 2


@pytest.mark.asyncio
async def test_execute_split_continues_on_child_failure(monkeypatch):
    # A failed child must NOT abort the rest — the caller persists whatever filled.
    async def fake_sleep(d):
        pass

    monkeypatch.setattr("app.execution_quality.splitter.asyncio.sleep", fake_sleep)
    calls = []

    async def submit_child(qty):
        calls.append(qty)
        if qty == Decimal("10"):
            raise RuntimeError("transient")
        return {"id": str(qty), "avg_deal_price": "100", "filled_total": str(qty * 100)}

    decision = SplitDecision(True, [Decimal("10"), Decimal("20"), Decimal("30")], 0.0)
    responses = await execute_split(submit_child, decision)
    assert len(calls) == 3  # all three attempted
    # The failed child is recorded as None; the other two have responses.
    assert responses[0] is None
    assert responses[1] is not None
    assert responses[2] is not None
