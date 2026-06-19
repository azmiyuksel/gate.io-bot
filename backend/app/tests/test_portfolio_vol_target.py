"""Portfolio-level volatility targeting."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.core.config import Settings
from app.services.risk.manager import portfolio_vol_target_multiplier


def _settings(**over):
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT")
    base.update(over)
    return Settings(**base)


def _D(values):
    return [Decimal(str(v)) for v in values]


TARGET = Decimal("0.02")
LO = Decimal("0.5")
HI = Decimal("1.5")


def test_not_enough_observations_returns_one():
    assert portfolio_vol_target_multiplier(_D([100, 101]), TARGET, LO, HI) == Decimal("1")


def test_flat_equity_returns_one():
    assert portfolio_vol_target_multiplier(_D([100] * 7), TARGET, LO, HI) == Decimal("1")


def test_hot_book_scales_down_to_floor():
    # ~10% per-step vol >> 2% target -> raw well below floor -> clamped to min.
    hot = _D([100, 110, 100, 110, 100, 110, 100])
    assert portfolio_vol_target_multiplier(hot, TARGET, LO, HI) == LO


def test_calm_book_scales_up_to_cap():
    # ~0.1% per-step vol << 2% target -> raw well above cap -> clamped to max.
    calm = _D([100, 100.1, 100, 100.1, 100, 100.1, 100])
    assert portfolio_vol_target_multiplier(calm, TARGET, LO, HI) == HI


def test_zero_target_disables():
    hot = _D([100, 110, 100, 110, 100, 110, 100])
    assert portfolio_vol_target_multiplier(hot, Decimal("0"), LO, HI) == Decimal("1")


def test_engine_portfolio_vol_mult_disabled_by_default(db_session):
    from app.services.trading_engine import TradingEngine

    with patch("app.services.trading_engine.get_settings", return_value=_settings(portfolio_vol_target_enabled=False)):
        engine = TradingEngine(db_session, AsyncMock())
        assert engine._portfolio_vol_mult() == Decimal("1")


def test_engine_portfolio_vol_mult_reads_snapshots(db_session):
    from app.models.entities import AccountSnapshot
    from app.services.trading_engine import TradingEngine

    # Seed a HOT equity curve -> multiplier should clamp to the floor (0.5).
    for v in [100, 110, 100, 110, 100, 110, 100]:
        db_session.add(AccountSnapshot(total_equity=Decimal(str(v)), source="exchange"))
    db_session.commit()

    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(portfolio_vol_target_enabled=True, portfolio_vol_target_pct=0.02,
                                      portfolio_vol_lookback=20, portfolio_vol_min_multiplier=0.5,
                                      portfolio_vol_max_multiplier=1.5)):
        engine = TradingEngine(db_session, AsyncMock())
        assert engine._portfolio_vol_mult() == Decimal("0.5")
