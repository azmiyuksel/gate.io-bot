"""Order/position reconciliation against the exchange.

Orders are persisted locally as ``open`` the moment they are submitted and were
never updated afterwards, so a crash or restart left the local state diverged
from Gate.io. This engine pulls the authoritative order state from the exchange,
updates local rows, fills position prices from real average deal prices and
records an audit trail in ``reconciliation_logs``.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import Order, Position, ReconciliationLog, SystemLog
from app.models.enums import LogLevel, OrderStatus, ReconcileAction
from app.services.exchange.gateio import GateIOClient

# Gate.io spot order status -> local OrderStatus
_STATUS_MAP = {
    "closed": OrderStatus.filled,
    "filled": OrderStatus.filled,
    "cancelled": OrderStatus.cancelled,
    "canceled": OrderStatus.cancelled,
    "open": OrderStatus.open,
}


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


class ReconciliationEngine:
    def __init__(self, db: Session, client: GateIOClient) -> None:
        self.db = db
        self.client = client

    def open_orders(self) -> list[Order]:
        return list(
            self.db.query(Order)
            .filter(Order.status == OrderStatus.open)
            .filter(Order.exchange_order_id.isnot(None))
            .all()
        )

    @staticmethod
    def _filled_quantity(remote: dict, original: Decimal) -> Decimal:
        if remote.get("filled_amount") is not None:
            return _to_decimal(remote["filled_amount"])
        if remote.get("left") is not None:
            return original - _to_decimal(remote["left"])
        if str(remote.get("status")) in ("closed", "filled"):
            return original
        return Decimal("0")

    @staticmethod
    def _fill_price(remote: dict) -> Decimal | None:
        for key in ("avg_deal_price", "fill_price", "price"):
            if remote.get(key):
                price = _to_decimal(remote[key])
                if price > 0:
                    return price
        return None

    async def reconcile_order(self, order: Order) -> ReconciliationLog:
        previous = str(order.status)
        if not order.exchange_order_id:
            return self._log(order, ReconcileAction.not_found, previous, previous,
                             Decimal("0"), "no exchange_order_id on local order")
        try:
            remote = await self.client.get_order(order.symbol, order.exchange_order_id)
        except Exception as exc:  # network / 404 / etc.
            return self._log(order, ReconcileAction.error, previous, previous,
                             Decimal("0"), f"exchange lookup failed: {exc}")

        remote_status = str(remote.get("status", "")).lower()
        mapped = _STATUS_MAP.get(remote_status, OrderStatus.open)
        original_qty = order.quantity or Decimal("0")
        filled = self._filled_quantity(remote, original_qty)

        if mapped == OrderStatus.open:
            return self._log(order, ReconcileAction.no_change, previous, previous,
                             filled, "still open on exchange")

        # Status changed -> update local order.
        order.status = mapped
        order.updated_at = datetime.now(UTC)
        fill_price = self._fill_price(remote)
        if fill_price is not None:
            order.price = fill_price

        if mapped == OrderStatus.filled and 0 < filled < original_qty:
            action = ReconcileAction.partially_filled
        elif mapped == OrderStatus.filled:
            action = ReconcileAction.filled
        else:
            action = ReconcileAction.cancelled

        # Keep the linked position entry price aligned with the real fill.
        if action in (ReconcileAction.filled, ReconcileAction.partially_filled) and fill_price:
            self._sync_position_price(order, fill_price)

        return self._log(order, action, previous, str(mapped), filled,
                         f"exchange status={remote_status}")

    def _sync_position_price(self, order: Order, fill_price: Decimal) -> None:
        if order.position_id is None:
            return
        position = self.db.get(Position, order.position_id)
        if position is not None and order.side.value == "buy":
            position.entry_price = fill_price

    async def reconcile_open_orders(self) -> list[ReconciliationLog]:
        logs = [await self.reconcile_order(order) for order in self.open_orders()]
        self.db.commit()
        return logs

    async def recover_on_startup(self) -> list[ReconciliationLog]:
        """Run once on boot to realign local state with the exchange."""
        logs = await self.reconcile_open_orders()
        changed = [log for log in logs if log.action not in (ReconcileAction.no_change,)]
        self.db.add(
            SystemLog(
                level=LogLevel.info,
                source="reconciliation",
                message=f"startup recovery reconciled {len(logs)} open orders, {len(changed)} changed",
            )
        )
        self.db.commit()
        return logs

    def _log(
        self,
        order: Order,
        action: ReconcileAction,
        previous_status: str,
        new_status: str,
        filled: Decimal,
        detail: str,
    ) -> ReconciliationLog:
        record = ReconciliationLog(
            order_id=order.id,
            exchange_order_id=order.exchange_order_id,
            symbol=order.symbol,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            filled_quantity=filled,
            detail=detail,
        )
        self.db.add(record)
        return record
