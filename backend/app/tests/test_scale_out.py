"""Partial profit taking (scale-out) at +R."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.models.entities import Position, Trade
from app.models.enums import OrderSide, PositionStatus
from app.services.strategy.signals import Signal  # noqa: F401 (parity with other tests)


def _settings(**over):
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT")
    base.update(over)
    return Settings(**base)


def _long_position(db, entry="100", initial_stop="96", qty="10"):
    pos = Position(
        symbol="BTC_USDT", side=OrderSide.buy, entry_price=Decimal(entry),
        quantity=Decimal(qty), stop_loss=Decimal(initial_stop),
        initial_stop_loss=Decimal(initial_stop), take_profit=Decimal("0"),
        status=PositionStatus.open,
    )
    db.add(pos)
    db.commit()
    return pos


@pytest.mark.asyncio
async def test_scale_out_banks_half_and_moves_to_breakeven(db_session):
    from app.services.trading_engine import TradingEngine

    pos = _long_position(db_session)  # entry 100, initial_stop 96 -> R=4, qty 10
    client = AsyncMock()
    # Sell 5 @ 104 (filled_total quote = 520 -> base 5).
    client.place_market_sell = AsyncMock(return_value={"id": "1", "avg_deal_price": "104", "filled_total": "520"})

    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(scale_out_enabled=True, scale_out_r_multiple=1.0,
                                      scale_out_fraction=0.5, trading_market="spot")):
        engine = TradingEngine(db_session, client)
        engine.notifier = AsyncMock()
        engine._amend_exchange_stop = AsyncMock()
        engine._cancel_exchange_stop = AsyncMock()
        # price 104 -> profit 4 == 1R -> triggers.
        await engine._maybe_scale_out(pos, Decimal("104"))

    db_session.refresh(pos)
    assert pos.scaled_out is True
    assert pos.quantity == Decimal("5")            # half closed
    assert pos.stop_loss == Decimal("100")          # moved to breakeven (entry)
    assert pos.breakeven_stop is True
    assert pos.realized_pnl == Decimal("20")        # (104-100)*5
    assert pos.status == PositionStatus.open
    engine._amend_exchange_stop.assert_awaited_once()
    # A closing Trade is recorded for the partial.
    trades = db_session.query(Trade).filter(Trade.symbol == "BTC_USDT").all()
    assert len(trades) == 1
    assert trades[0].side == OrderSide.sell


@pytest.mark.asyncio
async def test_scale_out_not_triggered_below_r(db_session):
    from app.services.trading_engine import TradingEngine

    pos = _long_position(db_session)  # R=4
    client = AsyncMock()
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(scale_out_enabled=True, scale_out_r_multiple=1.0,
                                      scale_out_fraction=0.5, trading_market="spot")):
        engine = TradingEngine(db_session, client)
        engine.notifier = AsyncMock()
        # price 103 -> profit 3 < 1R (4) -> no scale-out.
        await engine._maybe_scale_out(pos, Decimal("103"))

    db_session.refresh(pos)
    assert pos.scaled_out is False
    assert pos.quantity == Decimal("10")
    client.place_market_sell.assert_not_called()


@pytest.mark.asyncio
async def test_scale_out_fires_at_most_once(db_session):
    from app.services.trading_engine import TradingEngine

    pos = _long_position(db_session)
    pos.scaled_out = True
    db_session.commit()
    client = AsyncMock()
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(scale_out_enabled=True, scale_out_r_multiple=1.0,
                                      scale_out_fraction=0.5, trading_market="spot")):
        engine = TradingEngine(db_session, client)
        engine.notifier = AsyncMock()
        await engine._maybe_scale_out(pos, Decimal("110"))
    client.place_market_sell.assert_not_called()


@pytest.mark.asyncio
async def test_scale_out_disabled_by_default(db_session):
    from app.services.trading_engine import TradingEngine

    pos = _long_position(db_session)
    client = AsyncMock()
    with patch("app.services.trading_engine.get_settings", return_value=_settings(trading_market="spot")):
        engine = TradingEngine(db_session, client)
        engine.notifier = AsyncMock()
        await engine._maybe_scale_out(pos, Decimal("120"))
    db_session.refresh(pos)
    assert pos.scaled_out is False
    client.place_market_sell.assert_not_called()
