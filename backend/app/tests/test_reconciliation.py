from decimal import Decimal

from app.reconciliation.engine import ReconciliationEngine, _STATUS_MAP
from app.models.enums import OrderStatus


def test_status_map_covers_exchange_states() -> None:
    assert _STATUS_MAP["closed"] == OrderStatus.filled
    assert _STATUS_MAP["cancelled"] == OrderStatus.cancelled
    assert _STATUS_MAP["open"] == OrderStatus.open


def test_filled_quantity_from_left() -> None:
    qty = ReconciliationEngine._filled_quantity({"left": "0.4"}, Decimal("1.0"))
    assert qty == Decimal("0.6")


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
