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
from app.models.enums import (
    LogLevel,
    OrderSide,
    OrderStatus,
    PositionStatus,
    ReconcileAction,
)
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

    def recent_orders(self, limit: int = 100) -> list[Order]:
        """Return recently modified orders — not just open ones.

        This catches orders that were marked ``filled`` locally but may have
        been cancelled on the exchange (e.g. after a timeout), preventing
        silent state divergence.
        """
        return list(
            self.db.query(Order)
            .filter(Order.exchange_order_id.isnot(None))
            .filter(Order.status.in_([OrderStatus.open, OrderStatus.filled]))
            .order_by(Order.updated_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def _filled_quantity(remote: dict, original: Decimal, side: str = "buy") -> Decimal:
        # `filled_amount` is the base quantity filled (correct for both sides).
        if remote.get("filled_amount") is not None:
            return _to_decimal(remote["filled_amount"])
        # `left` is the outstanding amount in the order's `amount` unit: base for a
        # SELL (safe to subtract), but QUOTE for a market BUY — so only use it on sells.
        if side == "sell" and remote.get("left") is not None:
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

    @staticmethod
    def _fee_in_quote(remote: dict, symbol: str) -> Decimal:
        """Exchange fee, only when it is denominated in the quote currency so it
        can be subtracted from a quote-denominated PnL directly. A base- or
        points-denominated fee is skipped rather than mis-subtracted."""
        fee = _to_decimal(remote.get("fee"))
        if fee <= 0:
            return Decimal("0")
        ccy = str(remote.get("fee_currency") or "").upper()
        quote = symbol.split("_")[1].upper() if "_" in symbol else ""
        return fee if (ccy and quote and ccy == quote) else Decimal("0")

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
        original_qty = order.quantity or Decimal("0")
        filled = self._filled_quantity(remote, original_qty, order.side.value)

        # An IOC order (all our market orders are IOC) that fills part of the
        # request and cancels the rest reports status "cancelled" WITH filled > 0.
        # Treat that as a (partial) fill rather than a no-op cancellation.
        if remote_status in ("cancelled", "canceled") and filled > 0:
            mapped = OrderStatus.filled
        else:
            mapped = _STATUS_MAP.get(remote_status, OrderStatus.open)

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

        # Align the linked position with the real fill (price and, on a partial
        # fill, the actually-filled quantity).
        if action in (ReconcileAction.filled, ReconcileAction.partially_filled) and fill_price:
            self._sync_position(
                order, fill_price, filled, original_qty, self._fee_in_quote(remote, order.symbol)
            )

        return self._log(order, action, previous, str(mapped), filled,
                         f"exchange status={remote_status}")

    def _sync_position(
        self,
        order: Order,
        fill_price: Decimal,
        filled: Decimal,
        original: Decimal,
        fee: Decimal = Decimal("0"),
    ) -> None:
        if order.position_id is None:
            return
        position = self.db.get(Position, order.position_id)
        if position is None:
            return
        # An ENTRY order shares the position's side; a CLOSE order is the opposite
        # side. This disambiguates a short's close (a BUY) from a long's entry.
        is_entry = order.side == position.side
        if is_entry:
            position.entry_price = fill_price
            if 0 < filled < original:
                position.quantity = filled
            return

        # CLOSE order: recompute realized PnL from the authoritative exchange fill.
        # Overwrite (not accumulate) so re-reconciling the same close is idempotent
        # and never double-counts the PnL the engine already booked. Respect
        # direction — a SHORT (position.side == sell) profits when price falls.
        qty = filled if (filled and Decimal("0") < filled <= position.quantity) else position.quantity
        if position.side == OrderSide.sell:
            position.realized_pnl = (position.entry_price - fill_price) * qty - fee
        else:
            position.realized_pnl = (fill_price - position.entry_price) * qty - fee
        # A fully-filled close must mark the position closed so it is no longer
        # treated as open (and re-managed) by the trading engine.
        if not filled or filled >= position.quantity:
            position.status = PositionStatus.closed
            if position.closed_at is None:
                position.closed_at = datetime.now(UTC)

    async def reconcile_open_orders(self) -> list[ReconciliationLog]:
        logs = [await self.reconcile_order(order) for order in self.open_orders()]
        self.db.commit()
        # Also reconcile positions against the exchange (futures only) so a
        # position closed by the exchange stop while the local poll was down
        # does not linger as a ghost open position that manage_open_positions
        # keeps trying to manage. Order-only reconciliation misses this because
        # a conditional stop order's fill may not have a corresponding local
        # Order row (the stop was placed on the exchange, not tracked as an
        # Order in the local DB).
        await self.reconcile_positions()
        return logs

    async def reconcile_recent_orders(self, limit: int = 100) -> list[ReconciliationLog]:
        """Reconcile all recent orders (open + recently filled).

        Catches orders that were marked filled locally but got cancelled on
        the exchange, preventing silent state divergence.
        """
        orders = self.recent_orders(limit)
        logs = [await self.reconcile_order(order) for order in orders]
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

    async def reconcile_positions(self) -> list[ReconciliationLog]:
        """Reconcile locally-open positions against the exchange (futures only).

        For each locally-open position, query the exchange's position list. If
        the exchange reports the position as closed/flat (size 0 or absent), the
        local position is a GHOST — likely the exchange-side stop fired while the
        local poll was down. Mark it closed so manage_open_positions stops trying
        to manage it and reconciliation recovers the PnL from the stop order's
        fill (if any). Spot positions are skipped (no position list on spot; the
        balance check would require a full account reconciliation).

        Returns ReconciliationLog entries for each ghost position detected.
        """
        from app.core.config import get_settings

        if get_settings().trading_market.lower() != "futures":
            return []
        logs: list[ReconciliationLog] = []
        for position in self.db.query(Position).filter(Position.status == PositionStatus.open).all():
            try:
                fut_pos = await self.client.get_futures_position(position.symbol)
            except Exception:
                continue
            # If the exchange has no position or size 0, the local row is a ghost.
            if fut_pos is None:
                # Gate.io returns None when flat (no position object exists).
                # The old `continue` skipped this — the ghost was never caught
                # and manage_open_positions kept trying to manage a dead row.
                position.status = PositionStatus.closed
                position.closed_at = datetime.now(UTC)
                self.db.add(position)
                log = ReconciliationLog(
                    action=ReconcileAction.filled,
                    detail=f"ghost position {position.symbol} — exchange reports no position (flat), local marked closed",
                )
                self.db.add(log)
                logs.append(log)
                self.db.add(
                    SystemLog(
                        level=LogLevel.warning,
                        source="reconciliation",
                        message=f"ghost position {position.symbol}: exchange reports no position (flat), local marked closed",
                    )
                )
                continue
            size = fut_pos.get("size") or fut_pos.get("current_size") or 0
            if int(abs(_to_decimal(size))) == 0:
                # Ghost — the exchange closed it (stop/liquidation/manual). Mark
                # closed locally so we stop managing a dead position. PnL recovery
                # from the stop fill is handled by order reconciliation if a local
                # Order row exists; otherwise the realized PnL stays at its last
                # known value (conservative — don't fabricate a PnL we can't verify).
                position.status = PositionStatus.closed
                position.closed_at = datetime.now(UTC)
                self.db.add(position)
                log = ReconciliationLog(
                    action=ReconcileAction.filled,
                    detail=f"ghost position {position.symbol} closed on exchange but open locally — marked closed",
                )
                self.db.add(log)
                logs.append(log)
                self.db.add(
                    SystemLog(
                        level=LogLevel.warning,
                        source="reconciliation",
                        message=f"ghost position {position.symbol}: exchange reports flat, local marked closed",
                    )
                )
        if logs:
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
