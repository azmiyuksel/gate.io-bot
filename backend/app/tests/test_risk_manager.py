from decimal import Decimal

from app.services.risk.manager import RiskDecision


def test_risk_decision_shape() -> None:
    decision = RiskDecision(True, "approved", Decimal("1"), Decimal("90"), Decimal("120"))
    assert decision.allowed
    assert decision.take_profit > decision.stop_loss
