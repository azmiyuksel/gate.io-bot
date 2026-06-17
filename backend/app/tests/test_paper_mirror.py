"""Paper mirrors the live account's economics (no go-live surprises)."""
from decimal import Decimal

from app.core.config import Settings
from app.models.entities import StrategySettings
from app.paper_trading.mirror import resolve_paper_exec


def _settings(**over) -> Settings:
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT")
    base.update(over)
    return Settings(**base)


def _seed_strategy_settings(db) -> StrategySettings:
    ss = StrategySettings(
        name="capital_preservation_v1",
        max_capital_per_trade_pct=Decimal("0.05"),
        daily_max_loss_pct=Decimal("0.05"),
        weekly_max_loss_pct=Decimal("0.15"),
        max_open_positions=8,
        min_reward_risk=Decimal("1.5"),
        atr_multiplier=Decimal("2.0"),
        trailing_stop_pct=Decimal("0.015"),
    )
    db.add(ss)
    db.commit()
    return ss


def test_mirror_spot_is_long_only_unleveraged(db_session) -> None:
    _seed_strategy_settings(db_session)
    s = _settings(paper_mirror_live=True, trading_market="spot", market_data_interval="15m",
                  max_risk_per_trade_pct=0.02, max_total_exposure_pct=0.30,
                  max_account_drawdown_pct=0.15, paper_spot_taker_fee=0.001)
    ex = resolve_paper_exec(db_session, s)
    assert ex.mirror is True
    assert ex.market == "spot"
    assert ex.interval == "15m"
    assert ex.leverage == Decimal("1")
    assert ex.allow_short is False
    assert ex.funding_enabled is False
    assert ex.taker_fee == Decimal("0.001")
    # Sizing/limits come from the live config + StrategySettings.
    assert ex.risk_pct == Decimal("0.02")
    assert ex.notional_cap_pct == Decimal("0.05")
    assert ex.atr_stop_multiplier == Decimal("2.0")
    assert ex.tp_rr == Decimal("1.5")
    assert ex.daily_max_loss_pct == Decimal("0.05")
    assert ex.max_drawdown_pct == Decimal("0.15")
    assert ex.max_open_positions == 8
    assert ex.max_exposure_pct == Decimal("0.30")


def test_mirror_futures_uses_leverage_and_shorts(db_session) -> None:
    _seed_strategy_settings(db_session)
    s = _settings(paper_mirror_live=True, trading_market="futures", futures_leverage=5,
                  momentum_allow_short=True, funding_cost_enabled=True,
                  paper_taker_fee=0.0005)
    ex = resolve_paper_exec(db_session, s)
    assert ex.market == "futures"
    assert ex.leverage == Decimal("5")
    assert ex.allow_short is True
    assert ex.funding_enabled is True
    assert ex.taker_fee == Decimal("0.0005")  # futures fee, not spot


def test_standalone_mode_uses_paper_knobs(db_session) -> None:
    s = _settings(paper_mirror_live=False, paper_leverage=5.0,
                  paper_market_data_interval="5m", paper_position_risk_pct=0.005,
                  paper_taker_fee=0.0005, momentum_allow_short=True,
                  paper_max_capital_per_trade_pct=0.10)
    ex = resolve_paper_exec(db_session, s)
    assert ex.mirror is False
    assert ex.interval == "5m"
    assert ex.leverage == Decimal("5.0")
    assert ex.allow_short is True
    assert ex.risk_pct == Decimal("0.005")
    assert ex.notional_cap_pct == Decimal("0.10")
    assert ex.taker_fee == Decimal("0.0005")
