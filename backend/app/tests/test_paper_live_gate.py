"""Paper applies the same entry gates as the live engine (full parity)."""
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.market_data_quality.models import DataTradeStatus
from app.models.entities import PaperAccount
from app.paper_trading.engine import PaperTradingEngine
from app.paper_trading.models import PaperSide, TradingSignal


def _settings(**over) -> Settings:
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT",
                correlation_filter_enabled=False, mdq_pause_on_invalid=True)
    base.update(over)
    return Settings(**base)


class _Strat:
    name = "momentum_breakout_v1"


def _engine(db) -> PaperTradingEngine:
    acc = PaperAccount(name="default", cash_balance=Decimal("10000"), initial_balance=Decimal("10000"))
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return PaperTradingEngine(db, acc, strategy=_Strat())


def _signal() -> TradingSignal:
    return TradingSignal(symbol="BTC_USDT", side=PaperSide.buy, strength=0.8,
                         strategy="momentum_breakout_v1", timestamp=datetime.now(UTC),
                         metadata={"atr": "10", "direction": "long"})


def _candles(n=60):
    return [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1, "timestamp": i} for i in range(n)]


class _MDQRes:
    def __init__(self, status):
        self.trade_status = status


def _patch_mdq(monkeypatch, status):
    class _FakeMDQ:
        def __init__(self, db):
            pass

        def ingest(self, candles, symbol, interval, source="gateio"):
            return _MDQRes(status)

    monkeypatch.setattr("app.market_data_quality.engine.MarketDataQualityEngine", _FakeMDQ)


def _patch_regime(monkeypatch, allowed, mult):
    class _FakeRegime:
        def __init__(self, db):
            pass

        def update_regime(self, symbol, interval, candles):
            return None

        def should_trade(self, strategy_name, symbol, timeframe="1h"):
            return allowed, "test", Decimal(str(mult))

    monkeypatch.setattr("app.market_regime.engine.MarketRegimeEngine", _FakeRegime)


def _patch_health(monkeypatch, state, mult):
    class _FakeHealth:
        def __init__(self, db, **kw):
            pass

        def update_health(self, strategy_name):
            return {"state": state, "risk_multiplier": mult}

    monkeypatch.setattr("app.strategy_health.engine.StrategyHealthEngine", _FakeHealth)


@pytest.mark.asyncio
async def test_gate_blocks_on_invalid_data(db_session, monkeypatch) -> None:
    eng = _engine(db_session)
    _patch_mdq(monkeypatch, DataTradeStatus.invalid)
    allowed, _ = await eng._live_entry_gate("BTC_USDT", _candles(), _signal(), _settings())
    assert allowed is False


@pytest.mark.asyncio
async def test_gate_blocks_on_regime(db_session, monkeypatch) -> None:
    eng = _engine(db_session)
    _patch_mdq(monkeypatch, DataTradeStatus.clean)
    _patch_regime(monkeypatch, allowed=False, mult=1)
    allowed, _ = await eng._live_entry_gate("BTC_USDT", _candles(), _signal(), _settings())
    assert allowed is False


@pytest.mark.asyncio
async def test_gate_blocks_when_health_paused(db_session, monkeypatch) -> None:
    eng = _engine(db_session)
    _patch_mdq(monkeypatch, DataTradeStatus.clean)
    _patch_regime(monkeypatch, allowed=True, mult=1)
    _patch_health(monkeypatch, state="PAUSED", mult=0)
    allowed, _ = await eng._live_entry_gate("BTC_USDT", _candles(), _signal(), _settings())
    assert allowed is False


@pytest.mark.asyncio
async def test_gate_composes_risk_multiplier(db_session, monkeypatch) -> None:
    eng = _engine(db_session)
    # DEGRADED data (x0.5) * regime (x0.8) * health (x0.5) = 0.2
    _patch_mdq(monkeypatch, DataTradeStatus.degraded)
    _patch_regime(monkeypatch, allowed=True, mult=0.8)
    _patch_health(monkeypatch, state="HEALTHY", mult=0.5)
    allowed, mult = await eng._live_entry_gate(
        "BTC_USDT", _candles(), _signal(), _settings(mdq_degraded_risk_multiplier=0.5)
    )
    assert allowed is True
    assert mult == pytest.approx(Decimal("0.2"))


@pytest.mark.asyncio
async def test_gate_passes_clean(db_session, monkeypatch) -> None:
    eng = _engine(db_session)
    _patch_mdq(monkeypatch, DataTradeStatus.clean)
    _patch_regime(monkeypatch, allowed=True, mult=1)
    _patch_health(monkeypatch, state="HEALTHY", mult=1)
    allowed, mult = await eng._live_entry_gate("BTC_USDT", _candles(), _signal(), _settings())
    assert allowed is True
    assert mult == Decimal("1")
