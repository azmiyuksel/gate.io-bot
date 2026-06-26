"""Integration tests for the paper risk simulator's auto-pause gate.

Verifies that the mirror-relaxed auto-pause limits (daily loss / drawdown)
actually let the book keep trading through drawdowns that would have paused
the strict live thresholds — i.e. that the relaxation in ``resolve_paper_exec``
flows through ``PaperRiskSimulator.approve_signal`` correctly.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal


from app.core.config import Settings
from app.models.entities import PaperAccount, PaperEquityCurve, StrategySettings
from app.models.enums import PaperBotStatus
from app.paper_trading.models import MarketData, PaperSide, TradingSignal
from app.paper_trading.risk_simulator import PaperRiskSimulator


def _settings(**over) -> Settings:
    base = dict(
        environment="local", secret_key="t", fernet_key="t",
        trading_symbols="BTC_USDT",
        paper_mirror_live=True, trading_market="futures",
        paper_relax_mirror_limits=True,
        paper_max_daily_loss_pct=0.08, paper_max_drawdown_pct=0.30,
        max_account_drawdown_pct=0.20, max_total_exposure_pct=0.35,
        max_risk_per_trade_pct=0.025,
        paper_circuit_breaker_losses=0,  # disable breaker to isolate loss-pause
    )
    base.update(over)
    return Settings(**base)


def _seed_live_strategy_settings(db) -> StrategySettings:
    ss = StrategySettings(
        name="momentum_breakout_v1",
        max_capital_per_trade_pct=Decimal("0.05"),
        daily_max_loss_pct=Decimal("0.05"),  # strict live daily-loss
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
        cash_balance=Decimal("10000"),
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
    return acc


def _equity_point(db, account, equity: float, ts: datetime, drawdown: float = 0.0) -> None:
    db.add(PaperEquityCurve(
        account_id=account.id, equity=Decimal(str(equity)),
        cash_balance=Decimal(str(equity)),
        drawdown=Decimal(str(drawdown)), timestamp=ts,
    ))
    db.commit()


def _signal(symbol: str = "ETH_USDT") -> TradingSignal:
    return TradingSignal(
        symbol=symbol, side=PaperSide.buy, strength=0.8,
        strategy="momentum_breakout_v1", timestamp=datetime.now(UTC),
        metadata={"atr": "10", "entry": "100", "direction": "long"},
    )


def _data(symbol: str = "ETH_USDT") -> MarketData:
    return MarketData(symbol=symbol, timestamp=datetime.now(UTC),
                     price=100.0, volume=1.0, high=101.0, low=99.0)


def test_relaxed_limits_allow_entry_under_live_daily_loss_pause(db_session, monkeypatch) -> None:
    """A 6% daily loss would PAUSE paper under the strict live 5% threshold, but
    with relaxation to paper's 8%, the entry must still be APPROVED."""
    _seed_live_strategy_settings(db_session)
    s = _settings()
    monkeypatch.setattr("app.core.config.get_settings", lambda: s)
    account = _seed_account(db_session)

    # Equity now 9400 -> 6% daily loss (above live 5%, below relaxed 8%).
    # Seed the 24h peak as 10000 and current equity as 9400.
    now = datetime.now(UTC)
    _equity_point(db_session, account, 10000.0, now - timedelta(hours=1))
    account.cash_balance = Decimal("9400")
    db_session.commit()

    risk = PaperRiskSimulator(db_session, account)
    approved, reason = risk.approve_signal(_signal(), _data())
    assert approved, f"expected approved under relaxed threshold, got {reason}"


def test_strict_limits_pause_entry_when_relax_off(db_session, monkeypatch) -> None:
    """Same 6% loss with paper_relax_mirror_limits=False must PAUSE (daily_loss
    >= live 5%) — guards against the relaxation silently widening live parity."""
    _seed_live_strategy_settings(db_session)
    s = _settings(paper_relax_mirror_limits=False)
    monkeypatch.setattr("app.core.config.get_settings", lambda: s)
    account = _seed_account(db_session)

    now = datetime.now(UTC)
    _equity_point(db_session, account, 10000.0, now - timedelta(hours=1))
    account.cash_balance = Decimal("9400")
    db_session.commit()

    risk = PaperRiskSimulator(db_session, account)
    approved, reason = risk.approve_signal(_signal(), _data())
    assert not approved and reason == "daily_loss_limit_reached"
    assert account.status == PaperBotStatus.paused


def test_relaxed_drawdown_allows_entry(db_session, monkeypatch) -> None:
    """A 22% drawdown would pause under live 20% but the relaxed 30% lets the
    entry through."""
    _seed_live_strategy_settings(db_session)
    s = _settings()
    monkeypatch.setattr("app.core.config.get_settings", lambda: s)
    account = _seed_account(db_session)

    # Latest equity-curve row reports a 22% drawdown.
    _equity_point(db_session, account, 7800.0, datetime.now(UTC), drawdown=0.22)
    account.cash_balance = Decimal("7800")
    db_session.commit()

    risk = PaperRiskSimulator(db_session, account)
    approved, reason = risk.approve_signal(_signal(), _data())
    assert approved, f"expected approved under relaxed drawdown, got {reason}"


def test_hard_limit_still_pauses(db_session, monkeypatch) -> None:
    """Even relaxed, a loss beyond the relaxed threshold (9% > 8%) must pause —
    the relaxation is a floor, not a removal."""
    _seed_live_strategy_settings(db_session)
    s = _settings()
    monkeypatch.setattr("app.core.config.get_settings", lambda: s)
    account = _seed_account(db_session)

    now = datetime.now(UTC)
    _equity_point(db_session, account, 10000.0, now - timedelta(hours=1))
    account.cash_balance = Decimal("9100")  # 9% daily loss > relaxed 8%
    db_session.commit()

    risk = PaperRiskSimulator(db_session, account)
    approved, reason = risk.approve_signal(_signal(), _data())
    assert not approved and reason == "daily_loss_limit_reached"