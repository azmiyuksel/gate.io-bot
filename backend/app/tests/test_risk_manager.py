from decimal import Decimal

from app.services.risk.manager import RiskDecision


def test_risk_decision_shape() -> None:
    decision = RiskDecision(True, "approved", Decimal("1"), Decimal("90"), Decimal("120"))
    assert decision.allowed
    assert decision.take_profit > decision.stop_loss


def test_vol_target_multiplier_scales_inversely_to_volatility():
    from decimal import Decimal

    from app.services.risk.manager import vol_target_multiplier

    target = Decimal("0.02")
    lo, hi = Decimal("0.25"), Decimal("2.0")
    # ATR at target -> 1x; double the target vol -> halve size; calm -> capped at max.
    assert vol_target_multiplier(Decimal("0.02"), target, lo, hi) == Decimal("1")
    assert vol_target_multiplier(Decimal("0.04"), target, lo, hi) == Decimal("0.5")
    assert vol_target_multiplier(Decimal("0.001"), target, lo, hi) == hi   # capped
    assert vol_target_multiplier(Decimal("0.20"), target, lo, hi) == lo    # floored
    assert vol_target_multiplier(Decimal("0"), target, lo, hi) == Decimal("1")
