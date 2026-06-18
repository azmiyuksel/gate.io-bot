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


def test_trend_strategy_disables_take_profit(db_session, monkeypatch):
    """A trend-following (momentum) strategy must NOT set a fixed take-profit —
    a fixed R:R TP cuts the big winners that are its main edge. TP is set to 0
    so the position is managed only by trailing + breakeven + stop-loss."""
    from decimal import Decimal

    from app.core.config import get_settings
    from app.models.entities import StrategySettings
    from app.services.risk.manager import RiskManager

    settings = get_settings()
    monkeypatch.setattr(settings, "bot_enabled", True, raising=False)
    monkeypatch.setattr(settings, "risk_based_sizing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "max_risk_per_trade_pct", 0.02, raising=False)
    monkeypatch.setattr(settings, "max_total_exposure_pct", 0.30, raising=False)
    monkeypatch.setattr(settings, "max_net_exposure_pct", 0.30, raising=False)
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

    # Trend expectancy -> take_profit is 0 (disabled).
    trend = RiskManager(db_session).approve_entry(
        Decimal("10000"), Decimal("100"), Decimal("2"), expectancy_type="trend"
    )
    assert trend.allowed
    assert trend.take_profit == Decimal("0")
    # Stop still set (capital protection intact).
    assert trend.stop_loss > 0

    # Reversion expectancy -> take_profit set normally (1.5 R).
    reversion = RiskManager(db_session).approve_entry(
        Decimal("10000"), Decimal("100"), Decimal("2"), expectancy_type="reversion"
    )
    assert reversion.allowed
    assert reversion.take_profit > reversion.stop_loss


def test_net_exposure_guard_blocks_one_way_book(db_session, monkeypatch):
    """The net exposure cap must block a one-way long book that passes the gross
    cap — a 30% gross + 30% new long is 60% gross (blocked) but more importantly
    60% net long (blocked by the net cap before it ever gets there)."""
    from decimal import Decimal

    from app.core.config import get_settings
    from app.models.entities import Position, StrategySettings
    from app.models.enums import OrderSide, PositionStatus
    from app.services.risk.manager import RiskManager

    settings = get_settings()
    monkeypatch.setattr(settings, "bot_enabled", True, raising=False)
    monkeypatch.setattr(settings, "risk_based_sizing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "max_risk_per_trade_pct", 0.02, raising=False)
    monkeypatch.setattr(settings, "vol_targeting_enabled", False, raising=False)
    monkeypatch.setattr(settings, "drawdown_derisk_enabled", False, raising=False)
    # Tight net cap so the test triggers without huge positions.
    monkeypatch.setattr(settings, "max_total_exposure_pct", 0.50, raising=False)
    monkeypatch.setattr(settings, "max_net_exposure_pct", 0.20, raising=False)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    row.atr_multiplier = Decimal("2")
    row.min_reward_risk = Decimal("1.5")
    row.max_capital_per_trade_pct = Decimal("0.05")
    db_session.commit()

    # Existing long: 2500 notional on 10000 equity = 25% net long.
    db_session.add(Position(
        symbol="BTC_USDT", side=OrderSide.buy, entry_price=Decimal("100"),
        quantity=Decimal("25"), stop_loss=Decimal("90"), take_profit=Decimal("0"),
        status=PositionStatus.open,
    ))
    db_session.commit()

    # New long: 5% notional = 500. Post-trade net = 3000 = 30% > 20% cap -> blocked.
    decision = RiskManager(db_session).approve_entry(
        Decimal("10000"), Decimal("100"), Decimal("2"), side="long"
    )
    assert decision.allowed is False
    assert "max_net_exposure" in decision.reason


def test_net_exposure_guard_allows_market_neutral(db_session, monkeypatch):
    """A long + short book has low NET exposure even with high gross — the net
    cap should NOT block a market-neutral entry that the gross cap passes."""
    from decimal import Decimal

    from app.core.config import get_settings
    from app.models.entities import Position, StrategySettings
    from app.models.enums import OrderSide, PositionStatus
    from app.services.risk.manager import RiskManager

    settings = get_settings()
    monkeypatch.setattr(settings, "bot_enabled", True, raising=False)
    monkeypatch.setattr(settings, "risk_based_sizing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "max_risk_per_trade_pct", 0.02, raising=False)
    monkeypatch.setattr(settings, "vol_targeting_enabled", False, raising=False)
    monkeypatch.setattr(settings, "drawdown_derisk_enabled", False, raising=False)
    monkeypatch.setattr(settings, "max_total_exposure_pct", 0.50, raising=False)
    monkeypatch.setattr(settings, "max_net_exposure_pct", 0.20, raising=False)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    row.atr_multiplier = Decimal("2")
    row.min_reward_risk = Decimal("1.5")
    row.max_capital_per_trade_pct = Decimal("0.05")
    db_session.commit()

    # Existing long 2500 notional; new SHORT 500 -> post-trade net = 2000 = 20% (at cap, ok).
    db_session.add(Position(
        symbol="BTC_USDT", side=OrderSide.buy, entry_price=Decimal("100"),
        quantity=Decimal("25"), stop_loss=Decimal("90"), take_profit=Decimal("0"),
        status=PositionStatus.open,
    ))
    db_session.commit()
    decision = RiskManager(db_session).approve_entry(
        Decimal("10000"), Decimal("100"), Decimal("2"), side="short"
    )
    assert decision.allowed is True


def test_kelly_sizing_returns_none_without_track_record(db_session, monkeypatch):
    """No track record -> _kelly_scale returns None -> deterministic sizing."""
    from app.core.config import get_settings
    from app.services.risk.manager import RiskManager

    settings = get_settings()
    monkeypatch.setattr(settings, "kelly_sizing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "kelly_min_trades", 30, raising=False)
    rm = RiskManager(db_session)
    # No trades in the DB -> below min_trades -> None.
    assert rm._kelly_scale("long") is None


def test_kelly_sizing_scales_with_demonstrated_edge(db_session, monkeypatch):
    """With a strong track record (high win-rate + good payoff), ¼-Kelly scales
    size up (capped at 1.0). With a weak/no edge, it floors at 0.25."""
    from datetime import UTC, datetime

    from app.core.config import get_settings
    from app.models.entities import Trade
    from app.models.enums import OrderSide
    from app.services.risk.manager import RiskManager

    settings = get_settings()
    monkeypatch.setattr(settings, "kelly_sizing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "kelly_min_trades", 10, raising=False)
    monkeypatch.setattr(settings, "kelly_fraction", 0.25, raising=False)

    # 8 winning trades (pnl +50) and 2 losing trades (pnl -10) -> W=0.8, R=5.
    # Kelly f* = 0.8 - 0.2/5 = 0.76; quarter-Kelly = 0.19 -> floored at 0.25.
    for i in range(8):
        db_session.add(Trade(
            strategy_name="momentum_breakout_v1", symbol="BTC_USDT",
            side=OrderSide.buy, price=Decimal("100"), quantity=Decimal("1"),
            fee=Decimal("0"), realized_pnl=Decimal("50"),
            traded_at=datetime(2024, 1, 1 + i, tzinfo=UTC),
        ))
    for i in range(2):
        db_session.add(Trade(
            strategy_name="momentum_breakout_v1", symbol="BTC_USDT",
            side=OrderSide.buy, price=Decimal("100"), quantity=Decimal("1"),
            fee=Decimal("0"), realized_pnl=Decimal("-10"),
            traded_at=datetime(2024, 2, 1 + i, tzinfo=UTC),
        ))
    db_session.commit()

    rm = RiskManager(db_session)
    scale = rm._kelly_scale("long")
    assert scale is not None
    # 0.76 * 0.25 = 0.19 -> floored at 0.25.
    assert scale == Decimal("0.25")

    # A balanced book (5 wins +50, 5 losses -50) -> W=0.5, R=1 -> f*=0 -> floor 0.25.
    db_session.query(Trade).delete()
    for i in range(5):
        db_session.add(Trade(
            strategy_name="momentum_breakout_v1", symbol="BTC_USDT",
            side=OrderSide.buy, price=Decimal("100"), quantity=Decimal("1"),
            fee=Decimal("0"), realized_pnl=Decimal("50"),
            traded_at=datetime(2024, 1, 1 + i, tzinfo=UTC),
        ))
    for i in range(5):
        db_session.add(Trade(
            strategy_name="momentum_breakout_v1", symbol="BTC_USDT",
            side=OrderSide.buy, price=Decimal("100"), quantity=Decimal("1"),
            fee=Decimal("0"), realized_pnl=Decimal("-50"),
            traded_at=datetime(2024, 2, 1 + i, tzinfo=UTC),
        ))
    db_session.commit()
    scale = rm._kelly_scale("long")
    assert scale == Decimal("0.25")  # no edge -> floor


def test_kelly_sizing_capped_at_one(db_session, monkeypatch):
    """A very strong edge must not more than double the size (cap 1.0)."""
    from datetime import UTC, datetime

    from app.core.config import get_settings
    from app.models.entities import Trade
    from app.models.enums import OrderSide
    from app.services.risk.manager import RiskManager

    settings = get_settings()
    monkeypatch.setattr(settings, "kelly_sizing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "kelly_min_trades", 5, raising=False)
    monkeypatch.setattr(settings, "kelly_fraction", 1.0, raising=False)  # full Kelly for the cap test

    # 5 wins +100, 1 loss -10 -> W=5/6, R=10 -> f* = 0.833 - 0.167/10 ≈ 0.816.
    # Full Kelly = 0.816, capped at 1.0.
    for i in range(5):
        db_session.add(Trade(
            strategy_name="momentum_breakout_v1", symbol="BTC_USDT",
            side=OrderSide.buy, price=Decimal("100"), quantity=Decimal("1"),
            fee=Decimal("0"), realized_pnl=Decimal("100"),
            traded_at=datetime(2024, 1, 1 + i, tzinfo=UTC),
        ))
    db_session.add(Trade(
        strategy_name="momentum_breakout_v1", symbol="BTC_USDT",
        side=OrderSide.buy, price=Decimal("100"), quantity=Decimal("1"),
        fee=Decimal("0"), realized_pnl=Decimal("-10"),
        traded_at=datetime(2024, 2, 1, tzinfo=UTC),
    ))
    db_session.commit()
    rm = RiskManager(db_session)
    scale = rm._kelly_scale("long")
    assert scale is not None
    assert scale <= Decimal("1.0")
