"""Funding-rate carry as alpha: size UP when funding favors the entry."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.models.entities import Position
from app.models.enums import OrderSide, PositionStatus
from app.services.strategy.signals import Signal


def _settings(**over):
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT",
                trading_market="futures")
    base.update(over)
    return Settings(**base)


def test_carry_mult_disabled_returns_one(db_session):
    from app.services.trading_engine import TradingEngine

    with patch("app.services.trading_engine.get_settings", return_value=_settings(funding_carry_enabled=False)):
        engine = TradingEngine(db_session, AsyncMock())
        # Favorable for a long (negative rate) but carry disabled -> no boost.
        assert engine._funding_carry_mult("BTC_USDT", Decimal("-0.001"), is_short=False) == Decimal("1")


def test_carry_mult_below_threshold_returns_one(db_session):
    from app.services.trading_engine import TradingEngine

    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(funding_carry_enabled=True, funding_carry_threshold_pct=0.0005)):
        engine = TradingEngine(db_session, AsyncMock())
        # Favorable but small (< threshold) -> no boost.
        assert engine._funding_carry_mult("BTC_USDT", Decimal("-0.0003"), is_short=False) == Decimal("1")


def test_carry_mult_caps_at_max(db_session):
    from app.services.trading_engine import TradingEngine

    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(funding_carry_enabled=True, funding_carry_threshold_pct=0.0005,
                                      funding_carry_max_mult=1.25)):
        engine = TradingEngine(db_session, AsyncMock())
        # Long collects when rate is negative; at 2x threshold -> capped at max.
        assert engine._funding_carry_mult("BTC_USDT", Decimal("-0.001"), is_short=False) == Decimal("1.25")
        # Short collects when rate is positive.
        assert engine._funding_carry_mult("BTC_USDT", Decimal("0.001"), is_short=True) == Decimal("1.25")
        # Wrong-sign rate for the side (adverse) is not a carry boost here.
        assert engine._funding_carry_mult("BTC_USDT", Decimal("0.001"), is_short=False) == Decimal("1")


def test_carry_mult_ramps_linearly(db_session):
    from app.services.trading_engine import TradingEngine

    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(funding_carry_enabled=True, funding_carry_threshold_pct=0.0005,
                                      funding_carry_max_mult=1.5)):
        engine = TradingEngine(db_session, AsyncMock())
        # favorable = 0.00075 -> ramp = (0.00075-0.0005)/0.0005 = 0.5 -> 1 + 0.5*0.5 = 1.25
        assert engine._funding_carry_mult("BTC_USDT", Decimal("-0.00075"), is_short=False) == Decimal("1.25")


@pytest.mark.asyncio
async def test_check_funding_signal_boosts_on_favorable(db_session):
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    client.get_futures_funding_rate = AsyncMock(return_value={"r": "-0.001"})  # favorable for long
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(funding_signal_enabled=True, funding_signal_threshold_pct=0.0005,
                                      funding_carry_enabled=True, funding_carry_threshold_pct=0.0005,
                                      funding_carry_max_mult=1.25)):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
        mult = await engine._check_funding_signal("BTC_USDT", sig)
    assert mult == Decimal("1.25")


@pytest.mark.asyncio
async def test_check_funding_signal_still_derisks_on_adverse(db_session):
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    client.get_futures_funding_rate = AsyncMock(return_value={"r": "0.001"})  # adverse for long
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(funding_signal_enabled=True, funding_signal_threshold_pct=0.0005,
                                      funding_signal_risk_mult=0.5, funding_carry_enabled=True)):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
        mult = await engine._check_funding_signal("BTC_USDT", sig)
    assert mult == Decimal("0.5")


def test_final_size_clamped_to_exposure_after_boost(db_session, monkeypatch):
    """A funding boost (>1) applied after the risk manager must not breach the
    gross-exposure cap — _approve_risk_and_size re-clamps the final notional."""
    from app.models.entities import StrategySettings
    from app.services.trading_engine import TradingEngine

    settings = _settings(max_total_exposure_pct=0.30, drawdown_derisk_enabled=False, bot_enabled=True)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    row.atr_multiplier = Decimal("2")
    row.min_reward_risk = Decimal("1.5")
    row.max_capital_per_trade_pct = Decimal("0.05")
    db_session.commit()

    # Existing 2400 notional on 10000 equity; cap 30% = 3000.
    # The new entry (500 notional) is APPROVED (2400+500=2900 <= 3000), leaving
    # 600 of gross-exposure headroom. A 1.25x funding boost would push the new
    # notional to 625 (> 600) — the post-boost clamp must cap it at 600.
    db_session.add(Position(
        symbol="ETH_USDT", side=OrderSide.buy, entry_price=Decimal("100"),
        quantity=Decimal("24"), stop_loss=Decimal("90"), take_profit=Decimal("0"),
        status=PositionStatus.open,
    ))
    db_session.commit()

    with patch("app.services.trading_engine.get_settings", return_value=settings), \
         patch("app.services.risk.manager.get_settings", return_value=settings):
        engine = TradingEngine(db_session, AsyncMock())
        sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
        result = engine._approve_risk_and_size(
            "BTC_USDT", Decimal("10000"), sig,
            risk_mult=Decimal("1"), health_mult=Decimal("1"), data_risk_mult=Decimal("1"),
            funding_mult=Decimal("1.25"),
        )
    assert result is not None
    final_quantity, _, _ = result
    # Clamped to the 600 headroom (would have been 625 without the clamp).
    assert final_quantity * Decimal("100") == Decimal("600")
