"""Phase 2: live futures (long+short) execution + strategy mirroring."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.services.exchange.gateio import GateIOClient, OrderBelowMinimum
from app.services.strategy.factory import build_strategy
from app.services.strategy.momentum_breakout import MomentumBreakoutStrategy
from app.services.strategy.signals import CapitalPreservationStrategy, Signal


def _settings(**over):
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT")
    base.update(over)
    return Settings(**base)


# --- Strategy factory (paper/live share one source of truth) ---

def test_factory_defaults_to_momentum():
    assert isinstance(build_strategy("momentum_breakout_v1"), MomentumBreakoutStrategy)


def test_factory_hard_fails_on_unknown_strategy():
    # A typo must surface immediately — silently running the wrong strategy on
    # live capital is worse than a startup error. The old fallback-to-momentum
    # behaviour traded an unvalidated strategy under a mistyped name.
    import pytest

    with pytest.raises(ValueError, match="Unknown strategy"):
        build_strategy("unknown_xyz")


def test_factory_selects_capital_preservation():
    assert isinstance(build_strategy("capital_preservation_v1"), CapitalPreservationStrategy)


# --- Futures order request shaping ---

@pytest.mark.asyncio
async def test_futures_market_order_signs_size_for_short():
    client = GateIOClient()
    client.futures_contract_info = AsyncMock(return_value={"quanto_multiplier": "0.0001", "order_size_min": "1"})
    captured = {}

    async def fake_request(method, path, *, params=None, json_body=None):
        captured["method"], captured["path"], captured["body"] = method, path, json_body
        return {"id": "1", "fill_price": "100"}

    client.request = fake_request
    with patch("app.services.exchange.gateio.get_settings", return_value=_settings(futures_settle="usdt")):
        await client.place_futures_market_order("BTC_USDT", Decimal("1"), "short")
    # 1 BTC / 0.0001 = 10000 contracts, NEGATIVE for a short, IOC market (price 0).
    assert captured["path"] == "/futures/usdt/orders"
    assert captured["body"]["size"] == -10000
    assert captured["body"]["price"] == "0"
    assert captured["body"]["tif"] == "ioc"
    assert captured["body"]["reduce_only"] is False
    await client.close()


@pytest.mark.asyncio
async def test_futures_market_order_long_and_reduce_only():
    client = GateIOClient()
    client.futures_contract_info = AsyncMock(return_value={"quanto_multiplier": "0.001", "order_size_min": "1"})
    captured = {}

    async def fake_request(method, path, *, params=None, json_body=None):
        captured["body"] = json_body
        return {"id": "2"}

    client.request = fake_request
    with patch("app.services.exchange.gateio.get_settings", return_value=_settings()):
        await client.place_futures_market_order("ETH_USDT", Decimal("2"), "long", reduce_only=True)
    assert captured["body"]["size"] == 2000  # +, long
    assert captured["body"]["reduce_only"] is True
    await client.close()


@pytest.mark.asyncio
async def test_futures_order_below_minimum_raises():
    client = GateIOClient()
    client.futures_contract_info = AsyncMock(return_value={"quanto_multiplier": "0.0001", "order_size_min": "1"})
    client.request = AsyncMock(return_value={})
    with patch("app.services.exchange.gateio.get_settings", return_value=_settings()):
        with pytest.raises(OrderBelowMinimum):
            # 0.00005 / 0.0001 = 0.5 -> 0 contracts after rounding down.
            await client.place_futures_market_order("BTC_USDT", Decimal("0.00005"), "long")
    await client.close()


# --- Live engine: direction-aware routing (the short->buy bug fix) ---

@pytest.mark.asyncio
async def test_spot_skips_short_signal_without_buying(db_session):
    from app.models.entities import SystemLog
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    with patch("app.services.trading_engine.get_settings", return_value=_settings(trading_market="spot")):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "short", "short_breakout", Decimal("100"), Decimal("2"))
        await engine._execute_entry("BTC_USDT", sig, Decimal("1"), Decimal("104"), Decimal("97"), "momentum_breakout_v1")

    # Spot must NOT place any order for a short, and must log the skip.
    client.place_market_buy.assert_not_called()
    client.place_futures_market_order.assert_not_called()
    logs = db_session.query(SystemLog).filter(SystemLog.source == "short_skipped").all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_futures_routes_short_to_futures_order(db_session):
    from app.models.entities import Position
    from app.models.enums import OrderSide
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    client.place_futures_market_order = AsyncMock(return_value={"id": "9", "fill_price": "100"})
    client.set_futures_leverage = AsyncMock(return_value={})
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(trading_market="futures", futures_leverage=5)):
        engine = TradingEngine(db_session, client)
        engine.notifier = AsyncMock()
        engine._record_execution_quality = lambda **kw: None  # avoid nested-savepoint in test DB
        sig = Signal(True, "short", "short_breakout", Decimal("100"), Decimal("2"))
        await engine._execute_entry("BTC_USDT", sig, Decimal("1"), Decimal("104"), Decimal("97"), "momentum_breakout_v1")

    client.place_futures_market_order.assert_awaited_once()
    args = client.place_futures_market_order.await_args
    assert args.args[0] == "BTC_USDT"
    assert args.args[2] == "short"  # direction
    client.place_market_buy.assert_not_called()
    # A SHORT position is persisted with the correct side.
    pos = db_session.query(Position).filter(Position.symbol == "BTC_USDT").one()
    assert pos.side == OrderSide.sell
