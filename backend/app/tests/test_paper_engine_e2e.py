"""End-to-end tests for the paper trading engine's entry path under the
mirror-relaxed auto-pause limits.

Drives ``PaperTradingEngine.execute_signal`` (the post-strategy sizing+order
placement path) with a real DB-backed account, a real ``PaperRiskSimulator``,
a real ``resolve_paper_exec`` mirror, and a stubbed broker/order-manager so no
external exchange is touched. Asserts that an entry which would have been
PAUSED by the strict live daily-loss threshold is instead OPENED once the
relaxation flag widens that threshold, and that the corresponding PaperLog
diagnostic row is recorded.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.models.entities import (
    PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, StrategySettings,
)
from app.models.enums import OrderSide, PaperBotStatus, PaperOrderStatus, PaperOrderType
from app.paper_trading.engine import PaperTradingEngine
from app.paper_trading.models import MarketData, PaperSide, TradingSignal


def _settings(**over) -> Settings:
    base = dict(
        environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT",
        paper_mirror_live=True, trading_market="futures",
        paper_relax_mirror_limits=True,
        paper_max_daily_loss_pct=0.08, paper_max_drawdown_pct=0.30,
        max_account_drawdown_pct=0.20, max_total_exposure_pct=0.35,
        max_risk_per_trade_pct=0.025, paper_position_risk_pct=0.0075,
        paper_atr_stop_multiplier=2.0, paper_max_capital_per_trade_pct=0.14,
        paper_fallback_capital_pct=0.02, funding_cost_enabled=False,
        paper_circuit_breaker_losses=0, drawdown_derisk_enabled=False,
        paper_kelly_enabled=False, risk_based_sizing_enabled=True,
        paper_taker_fee=0.0005, paper_maker_fee=0.0002,
        eq_default_spread=0.0001, momentum_allow_short=True,
    )
    base.update(over)
    return Settings(**base)


def _seed_live_strategy_settings(db) -> StrategySettings:
    ss = StrategySettings(
        name="momentum_breakout_v1",
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


def _seed_account(db) -> PaperAccount:
    acc = PaperAccount(
        name="default",
        cash_balance=Decimal("9400"),
        initial_balance=Decimal("10000"),
        status=PaperBotStatus.running,
        max_daily_loss_pct=Decimal("0.05"),
        max_drawdown_pct=Decimal("0.20"),
        max_exposure_pct=Decimal("5"),
        max_open_positions=8,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    # Seed a 10000 peak 1h ago so the 24h rolling loss is 6%.
    db.add(PaperEquityCurve(
        account_id=acc.id, equity=Decimal("10000"),
        cash_balance=Decimal("10000"),
        drawdown=Decimal("0"), timestamp=datetime.now(UTC) - timedelta(hours=1),
    ))
    db.commit()
    return acc


def _signal() -> TradingSignal:
    return TradingSignal(
        symbol="ETH_USDT", side=PaperSide.buy, strength=0.8,
        strategy="momentum_breakout_v1", timestamp=datetime.now(UTC),
        metadata={"atr": "2.0", "entry": "100.0", "direction": "long"},
    )


def _data() -> MarketData:
    return MarketData(symbol="ETH_USDT", timestamp=datetime.now(UTC),
                      price=100.0, volume=1.0, high=101.0, low=99.0)


def _patch_settings(monkeypatch, s):
    """Patch the (lru_cached) settings factory on every module that imports it
    at module load (engine) or re-resolves app.core.config.get_settings."""
    import app.paper_trading.engine as engine_mod
    import app.paper_trading.mirror as mirror_mod
    import app.paper_trading.broker as broker_mod
    import app.paper_trading.risk_simulator as risk_mod

    monkeypatch.setattr("app.core.config.get_settings", lambda: s)
    for mod in (engine_mod, mirror_mod, broker_mod, risk_mod):
        if hasattr(mod, "get_settings"):
            monkeypatch.setattr(mod, "get_settings", lambda: s)


@pytest.mark.asyncio
async def test_execute_signal_opens_trade_under_relaxed_limits(db_session, monkeypatch):
    """6% daily loss > live 5% but < relaxed 8%: trade must OPEN."""
    _seed_live_strategy_settings(db_session)
    s = _settings()
    _patch_settings(monkeypatch, s)
    account = _seed_account(db_session)

    engine = PaperTradingEngine(db_session, account)
    # Stub the order manager so a PaperOrder row is created without the broker's
    # margin/funding/execution-simulator machinery.
    created = PaperOrder(
        account_id=account.id, symbol="ETH_USDT", side=OrderSide.buy,
        order_type=PaperOrderType.market, status=PaperOrderStatus.filled,
        requested_quantity=Decimal("1"), filled_quantity=Decimal("1"),
        average_fill_price=Decimal("100"),
    )
    db_session.add(created)
    db_session.commit()
    with patch.object(engine.order_manager, "execute_signal", return_value=created) as mock_om:
        await engine.execute_signal(_signal(), _data())
    db_session.flush()  # flush batched PaperLog writes before querying

    # The risk gate approved, so no risk_check rejection log for this symbol.
    rejections = (
        db_session.query(PaperLog)
        .filter(PaperLog.account_id == account.id, PaperLog.event == "risk_check")
        .all()
    )
    reject_reasons = [r.payload.get("reason") for r in rejections]
    assert "daily_loss_limit_reached" not in reject_reasons
    # Order placement was reached and the account is still RUNNING.
    assert account.status == PaperBotStatus.running
    mock_om.assert_called_once()


@pytest.mark.asyncio
async def test_execute_signal_paused_under_strict_limits(db_session, monkeypatch):
    """Same 6% loss with paper_relax_mirror_limits=False: PAUSED, no trade."""
    _seed_live_strategy_settings(db_session)
    s = _settings(paper_relax_mirror_limits=False)
    _patch_settings(monkeypatch, s)
    account = _seed_account(db_session)

    engine = PaperTradingEngine(db_session, account)
    with patch.object(engine.order_manager, "execute_signal", return_value=None) as mock_om:
        await engine.execute_signal(_signal(), _data())
    db_session.flush()  # flush batched PaperLog writes before querying

    # Risk gate rejected with daily_loss_limit_reached and paused the account.
    assert account.status == PaperBotStatus.paused
    rejections = (
        db_session.query(PaperLog)
        .filter(PaperLog.account_id == account.id, PaperLog.event == "risk_check")
        .all()
    )
    reject_reasons = [r.payload.get("reason") for r in rejections]
    assert "daily_loss_limit_reached" in reject_reasons
    mock_om.assert_not_called()