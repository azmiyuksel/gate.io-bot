"""Live-engine strategy filters: per-symbol guard + multi-timeframe confirmation."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.models.entities import Position, SystemLog
from app.models.enums import OrderSide, PositionStatus
from app.services.strategy.signals import Signal


def _settings(**over):
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT")
    base.update(over)
    return Settings(**base)


def _open_position(db, symbol="BTC_USDT", side=OrderSide.buy):
    pos = Position(
        symbol=symbol,
        side=side,
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("130"),
        status=PositionStatus.open,
    )
    db.add(pos)
    db.commit()
    return pos


def test_has_open_repository(db_session) -> None:
    from app.repositories.trading import PositionRepository

    repo = PositionRepository(db_session)
    assert repo.has_open("BTC_USDT") is False
    _open_position(db_session)
    assert repo.has_open("BTC_USDT") is True
    assert repo.has_open("ETH_USDT") is False


@pytest.mark.asyncio
async def test_scan_symbol_skips_when_position_already_open(db_session) -> None:
    from app.services.trading_engine import TradingEngine

    _open_position(db_session, "BTC_USDT")
    client = AsyncMock()
    with patch("app.services.trading_engine.get_settings", return_value=_settings()):
        engine = TradingEngine(db_session, client)
        await engine.scan_symbol("BTC_USDT", Decimal("10000"))

    # No market data fetched and the skip is logged — the entry is short-circuited
    # before any strategy evaluation.
    client.candles.assert_not_called()
    logs = db_session.query(SystemLog).filter(SystemLog.source == "already_in_position").all()
    assert len(logs) == 1


def _htf_candles(closes):
    return [{"close": c, "high": c, "low": c, "open": c, "volume": 1} for c in closes]


@pytest.mark.asyncio
async def test_mtf_filter_blocks_long_in_htf_downtrend(db_session) -> None:
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    # Descending closes => last is the lowest => below the EMA50 => HTF downtrend.
    client.candles = AsyncMock(return_value=_htf_candles([Decimal(str(200 - i)) for i in range(60)]))
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(strategy_mtf_enabled=True, strategy_mtf_interval="4h")):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
        allowed = await engine._check_mtf_filter("BTC_USDT", sig)

    assert allowed is False
    logs = db_session.query(SystemLog).filter(SystemLog.source == "mtf_filter").all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_mtf_filter_allows_long_in_htf_uptrend(db_session) -> None:
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    # Ascending closes => last is the highest => above the EMA50 => HTF uptrend.
    client.candles = AsyncMock(return_value=_htf_candles([Decimal(str(100 + i)) for i in range(60)]))
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(strategy_mtf_enabled=True, strategy_mtf_interval="4h")):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "long_breakout", Decimal("160"), Decimal("2"))
        assert await engine._check_mtf_filter("BTC_USDT", sig) is True


@pytest.mark.asyncio
async def test_mtf_filter_noop_when_disabled(db_session) -> None:
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(strategy_mtf_enabled=False)):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
        assert await engine._check_mtf_filter("BTC_USDT", sig) is True
    client.candles.assert_not_called()
