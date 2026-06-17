from decimal import Decimal

from app.reconciliation.engine import ReconciliationEngine, _STATUS_MAP
from app.models.enums import OrderStatus


def test_status_map_covers_exchange_states() -> None:
    assert _STATUS_MAP["closed"] == OrderStatus.filled
    assert _STATUS_MAP["cancelled"] == OrderStatus.cancelled
    assert _STATUS_MAP["open"] == OrderStatus.open


def test_filled_quantity_from_left_on_sell() -> None:
    # `left` is the outstanding BASE amount on a sell, so original - left is filled.
    qty = ReconciliationEngine._filled_quantity({"left": "0.4"}, Decimal("1.0"), "sell")
    assert qty == Decimal("0.6")


def test_filled_quantity_ignores_left_on_buy() -> None:
    # On a market BUY `left` is QUOTE, not base, so it must NOT be subtracted.
    qty = ReconciliationEngine._filled_quantity({"left": "0.4"}, Decimal("1.0"), "buy")
    assert qty == Decimal("0")


def test_filled_quantity_closed_without_fields() -> None:
    qty = ReconciliationEngine._filled_quantity({"status": "closed"}, Decimal("2.0"))
    assert qty == Decimal("2.0")


def test_fill_price_prefers_avg_deal_price() -> None:
    price = ReconciliationEngine._fill_price(
        {"avg_deal_price": "101.5", "fill_price": "100", "price": "99"}
    )
    assert price == Decimal("101.5")


def test_fill_price_none_when_absent() -> None:
    assert ReconciliationEngine._fill_price({"price": "0"}) is None


async def test_reconcile_partial_fill_on_cancelled_ioc(db_session) -> None:
    """An IOC buy that partially fills then cancels must sync the position
    price AND quantity, and be recorded as partially_filled (not cancelled)."""
    from app.models.entities import Order, Position
    from app.models.enums import OrderSide, ReconcileAction

    position = Position(
        symbol="BTC_USDT",
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("130"),
    )
    db_session.add(position)
    db_session.flush()
    order = Order(
        exchange_order_id="abc",
        position_id=position.id,
        symbol="BTC_USDT",
        side=OrderSide.buy,
        status=OrderStatus.open,
        price=Decimal("100"),
        quantity=Decimal("1"),
    )
    db_session.add(order)
    db_session.commit()

    class FakeClient:
        async def get_order(self, symbol, order_id):
            return {"status": "cancelled", "filled_amount": "0.6", "avg_deal_price": "101"}

    log = await ReconciliationEngine(db_session, FakeClient()).reconcile_order(order)
    assert log.action == ReconcileAction.partially_filled
    assert order.status == OrderStatus.filled
    # Same session => `position` is the instance _sync_position mutated.
    assert position.entry_price == Decimal("101")
    assert position.quantity == Decimal("0.6")


async def test_reconcile_long_close_sets_pnl_and_closes(db_session) -> None:
    """Reconciling a long's SELL close must recompute realized PnL from the real
    fill (price-drift fix), subtract a quote-denominated fee, and mark the
    position closed — not leave it open with a wrong-sign PnL."""
    from app.models.entities import Order, Position
    from app.models.enums import OrderSide, PositionStatus, ReconcileAction

    position = Position(
        symbol="BTC_USDT",
        side=OrderSide.buy,
        entry_price=Decimal("100"),
        quantity=Decimal("2"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("130"),
    )
    db_session.add(position)
    db_session.flush()
    order = Order(
        exchange_order_id="sell-1",
        position_id=position.id,
        symbol="BTC_USDT",
        side=OrderSide.sell,
        status=OrderStatus.open,
        price=Decimal("110"),
        quantity=Decimal("2"),
    )
    db_session.add(order)
    db_session.commit()

    class FakeClient:
        async def get_order(self, symbol, order_id):
            return {
                "status": "closed",
                "filled_amount": "2",
                "avg_deal_price": "110",
                "fee": "1.5",
                "fee_currency": "USDT",
            }

    log = await ReconciliationEngine(db_session, FakeClient()).reconcile_order(order)
    assert log.action == ReconcileAction.filled
    # (110 - 100) * 2 - 1.5 fee
    assert position.realized_pnl == Decimal("18.5")
    assert position.status == PositionStatus.closed
    assert position.closed_at is not None
