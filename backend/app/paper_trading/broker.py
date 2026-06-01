from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import PaperAccount, PaperLog, PaperOrder, PaperPosition, PaperTrade
from app.models.enums import LogLevel, OrderSide, PaperOrderStatus, PaperOrderType
from app.paper_trading.execution_simulator import ExecutionSimulator
from app.paper_trading.models import MarketData, PaperExecution, PaperSide, TradingSignal


class PaperBroker:
    def __init__(self, db: Session, account: PaperAccount, simulator: ExecutionSimulator | None = None) -> None:
        self.db = db
        self.account = account
        self.simulator = simulator or ExecutionSimulator()

    def submit_signal(self, signal: TradingSignal, quantity: Decimal, data: MarketData) -> PaperOrder:
        order = PaperOrder(
            account_id=self.account.id,
            symbol=signal.symbol,
            side=OrderSide(signal.side.value),
            order_type=PaperOrderType.market,
            status=PaperOrderStatus.pending,
            requested_quantity=quantity,
            signal={
                "symbol": signal.symbol,
                "side": signal.side.value,
                "strength": signal.strength,
                "strategy": signal.strategy,
                "timestamp": signal.timestamp.isoformat(),
                "metadata": signal.metadata,
            },
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        execution = self.simulator.execute_market(order.id, signal.side, float(quantity), data)
        self.apply_execution(order, execution)
        return order

    def apply_execution(self, order: PaperOrder, execution: PaperExecution) -> None:
        order.filled_quantity = Decimal(str(execution.filled_quantity))
        order.average_fill_price = Decimal(str(execution.average_price))
        order.fee_paid = Decimal(str(execution.fee))
        order.latency_ms = execution.latency_ms
        order.status = PaperOrderStatus.partially_filled if execution.partial else PaperOrderStatus.filled
        order.filled_at = datetime.now(UTC)
        if execution.side == PaperSide.buy:
            self._apply_buy(order, execution)
        else:
            self._apply_sell(order, execution)
        self.db.add(
            PaperTrade(
                account_id=self.account.id,
                order_id=order.id,
                symbol=order.symbol,
                side=OrderSide(execution.side.value),
                price=Decimal(str(execution.average_price)),
                quantity=Decimal(str(execution.filled_quantity)),
                fee=Decimal(str(execution.fee)),
                realized_pnl=Decimal("0"),
            )
        )
        self._log("order_filled", f"{order.side} {order.symbol} qty={execution.filled_quantity}")
        self.db.commit()

    def close_position(self, position: PaperPosition, data: MarketData, reason: str) -> None:
        execution = self.simulator.execute_market(
            order_id=0,
            side=PaperSide.sell,
            quantity=float(position.quantity),
            data=data,
        )
        exit_price = Decimal(str(execution.average_price))
        pnl = (exit_price - position.average_entry_price) * position.quantity - Decimal(str(execution.fee))
        self.account.cash_balance += exit_price * position.quantity - Decimal(str(execution.fee))
        self.account.realized_pnl += pnl
        position.realized_pnl += pnl
        position.is_open = False
        position.closed_at = datetime.now(UTC)
        self.db.add(
            PaperTrade(
                account_id=self.account.id,
                order_id=None,
                symbol=position.symbol,
                side=OrderSide.sell,
                price=exit_price,
                quantity=position.quantity,
                fee=Decimal(str(execution.fee)),
                realized_pnl=pnl,
            )
        )
        self._log("trade_closed", f"{position.symbol} closed: {reason}", {"pnl": str(pnl)})
        self.db.commit()

    def _apply_buy(self, order: PaperOrder, execution: PaperExecution) -> None:
        quantity = Decimal(str(execution.filled_quantity))
        price = Decimal(str(execution.average_price))
        fee = Decimal(str(execution.fee))
        total_cost = quantity * price + fee
        if self.account.cash_balance < total_cost:
            order.status = PaperOrderStatus.rejected
            self._log("order_rejected", "insufficient paper cash")
            return
        self.account.cash_balance -= total_cost
        existing = (
            self.db.query(PaperPosition)
            .filter(
                PaperPosition.account_id == self.account.id,
                PaperPosition.symbol == order.symbol,
                PaperPosition.is_open.is_(True),
            )
            .first()
        )
        if existing:
            total_qty = existing.quantity + quantity
            existing.average_entry_price = (
                (existing.average_entry_price * existing.quantity) + (price * quantity)
            ) / total_qty
            existing.quantity = total_qty
            existing.last_price = price
        else:
            self.db.add(
                PaperPosition(
                    account_id=self.account.id,
                    symbol=order.symbol,
                    quantity=quantity,
                    average_entry_price=price,
                    last_price=price,
                    stop_loss=price * Decimal("0.98"),
                    take_profit=price * Decimal("1.04"),
                )
            )

    def _apply_sell(self, order: PaperOrder, execution: PaperExecution) -> None:
        position = (
            self.db.query(PaperPosition)
            .filter(PaperPosition.account_id == self.account.id, PaperPosition.symbol == order.symbol, PaperPosition.is_open.is_(True))
            .first()
        )
        if position:
            self.close_position(position, MarketData(order.symbol, datetime.now(UTC), execution.average_price), "signal_sell")

    def _log(self, event: str, message: str, payload: dict | None = None) -> None:
        self.db.add(
            PaperLog(
                account_id=self.account.id,
                level=LogLevel.info,
                event=event,
                message=message,
                payload=payload or {},
            )
        )
