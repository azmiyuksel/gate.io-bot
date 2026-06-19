"""Order-book pegged maker entry price."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.services.strategy.signals import Signal


def _settings(**over):
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT")
    base.update(over)
    return Settings(**base)


def _book(best_bid, best_ask):
    return {"bids": [[str(best_bid), "10"]], "asks": [[str(best_ask), "10"]]}


@pytest.mark.asyncio
async def test_peg_disabled_returns_signal_price(db_session):
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    with patch("app.services.trading_engine.get_settings", return_value=_settings(maker_peg_enabled=False)):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "x", Decimal("100"), Decimal("2"))
        assert await engine._maker_peg_price("BTC_USDT", sig) == Decimal("100")
    client.get_order_book.assert_not_called()


@pytest.mark.asyncio
async def test_peg_long_joins_best_bid(db_session):
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    client.get_order_book = AsyncMock(return_value=_book("99", "101"))
    with patch("app.services.trading_engine.get_settings", return_value=_settings(maker_peg_enabled=True)):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "x", Decimal("100"), Decimal("2"))
        # offset 0 -> join best bid 99 (below signal 100, a better maker price).
        assert await engine._maker_peg_price("BTC_USDT", sig) == Decimal("99")


@pytest.mark.asyncio
async def test_peg_long_bounded_by_signal_and_stays_maker(db_session):
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    client.get_order_book = AsyncMock(return_value=_book("99.5", "101"))
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(maker_peg_enabled=True, maker_peg_offset_pct=0.02)):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "x", Decimal("100"), Decimal("2"))
        # 99.5*1.02 = 101.49 -> capped at signal 100 (never chase past signal),
        # and 100 < best_ask 101 so it stays a maker.
        assert await engine._maker_peg_price("BTC_USDT", sig) == Decimal("100")


@pytest.mark.asyncio
async def test_peg_short_joins_best_ask(db_session):
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    client.get_order_book = AsyncMock(return_value=_book("99", "101"))
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(maker_peg_enabled=True, trading_market="futures")):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "short", "x", Decimal("100"), Decimal("2"))
        # max(101, signal 100) = 101, above best bid 99 -> maker sell at the ask.
        assert await engine._maker_peg_price("BTC_USDT", sig) == Decimal("101")


@pytest.mark.asyncio
async def test_peg_fetch_failure_falls_back_to_signal(db_session):
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    client.get_order_book = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("app.services.trading_engine.get_settings", return_value=_settings(maker_peg_enabled=True)):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "x", Decimal("100"), Decimal("2"))
        assert await engine._maker_peg_price("BTC_USDT", sig) == Decimal("100")


@pytest.mark.asyncio
async def test_peg_empty_book_falls_back_to_signal(db_session):
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    client.get_order_book = AsyncMock(return_value={"bids": [], "asks": []})
    with patch("app.services.trading_engine.get_settings", return_value=_settings(maker_peg_enabled=True)):
        engine = TradingEngine(db_session, client)
        sig = Signal(True, "long", "x", Decimal("100"), Decimal("2"))
        assert await engine._maker_peg_price("BTC_USDT", sig) == Decimal("100")
