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


def test_risk_based_sizing_targets_fixed_risk(db_session, monkeypatch):
    from decimal import Decimal

    from app.core.config import get_settings
    from app.models.entities import StrategySettings
    from app.services.risk.manager import RiskManager

    settings = get_settings()
    monkeypatch.setattr(settings, "bot_enabled", True, raising=False)
    monkeypatch.setattr(settings, "max_risk_per_trade_pct", 0.02, raising=False)
    monkeypatch.setattr(settings, "max_total_exposure_pct", 0.30, raising=False)
    monkeypatch.setattr(settings, "vol_targeting_enabled", False, raising=False)
    monkeypatch.setattr(settings, "drawdown_derisk_enabled", False, raising=False)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    row.atr_multiplier = Decimal("2")
    row.min_reward_risk = Decimal("1.5")
    row.max_capital_per_trade_pct = Decimal("0.05")
    db_session.commit()

    equity, entry, atr = Decimal("10000"), Decimal("100"), Decimal("30")
    # risk_per_unit = atr*atr_multiplier = 60; stop=40, tp=190 (valid).

    # Notional mode ignores stop distance: a fixed 5-unit notional with a wide
    # stop (risk/unit=60) implies a 300 loss, breaching the 200 per-trade cap.
    monkeypatch.setattr(settings, "risk_based_sizing_enabled", False, raising=False)
    notional = RiskManager(db_session).approve_entry(equity, entry, atr)
    assert not notional.allowed
    assert notional.reason.startswith("excessive_risk_per_trade")

    # Risk-based mode sizes DOWN so loss-to-stop == 2% of equity (200/60) and trades.
    monkeypatch.setattr(settings, "risk_based_sizing_enabled", True, raising=False)
    risk = RiskManager(db_session).approve_entry(equity, entry, atr)
    assert risk.allowed
    assert risk.quantity == Decimal("200") / Decimal("60")
    assert risk.quantity * (entry - risk.stop_loss) == Decimal("200")
