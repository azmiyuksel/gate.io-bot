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


def test_drawdown_risk_multiplier_grades_with_drawdown():
    from decimal import Decimal

    from app.services.risk.manager import drawdown_risk_multiplier

    maxdd = Decimal("0.15")
    assert drawdown_risk_multiplier(Decimal("0"), maxdd) == Decimal("1")      # no DD
    assert drawdown_risk_multiplier(Decimal("0.075"), maxdd) == Decimal("0.5")  # halfway
    assert drawdown_risk_multiplier(Decimal("0.15"), maxdd) == Decimal("0")   # at limit
    # Floor respected; never exceeds 1.
    assert drawdown_risk_multiplier(Decimal("0.15"), maxdd, Decimal("0.2")) == Decimal("0.2")


def test_approve_entry_blocked_when_bot_disabled(db_session, monkeypatch):
    from decimal import Decimal

    from app.core.config import get_settings
    from app.services.risk.manager import RiskManager

    monkeypatch.setattr(get_settings(), "bot_enabled", False, raising=False)
    decision = RiskManager(db_session).approve_entry(Decimal("10000"), Decimal("100"), Decimal("2"))
    assert decision.allowed is False
    assert decision.reason == "bot_disabled"


def test_approve_entry_needs_both_flags(db_session, monkeypatch):
    from decimal import Decimal

    from app.core.config import get_settings
    from app.models.entities import StrategySettings
    from app.services.risk.manager import RiskManager

    # BOT_ENABLED on, but the strategy flag still off -> blocked at the strategy gate.
    monkeypatch.setattr(get_settings(), "bot_enabled", True, raising=False)
    blocked = RiskManager(db_session).approve_entry(Decimal("10000"), Decimal("100"), Decimal("2"))
    assert blocked.reason == "strategy_disabled"

    # Both flags on -> the entry is approved (sizing/levels computed).
    settings_row = db_session.query(StrategySettings).first()
    settings_row.is_enabled = True
    db_session.commit()
    approved = RiskManager(db_session).approve_entry(Decimal("10000"), Decimal("100"), Decimal("2"))
    assert approved.allowed is True
