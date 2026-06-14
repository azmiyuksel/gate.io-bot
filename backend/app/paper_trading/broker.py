import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import PaperAccount, PaperLog, PaperOrder, PaperPosition, PaperTrade
from app.models.enums import LogLevel, OrderSide, PaperOrderStatus, PaperOrderType
from app.paper_trading.execution_simulator import ExecutionSimulator
from app.paper_trading.models import MarketData, PaperExecution, PaperSide, TradingSignal

logger = logging.getLogger(__name__)


class PaperBroker:
    def __init__(self, db: Session, account: PaperAccount, simulator: ExecutionSimulator | None = None) -> None:
        self.db = db
        self.account = account
        self.simulator = simulator or ExecutionSimulator()

    def submit_signal(self, signal: TradingSignal, quantity: Decimal, data: MarketData) -> PaperOrder:
        signal_time = signal.timestamp
        submission_time = datetime.now(UTC)
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

        # Record Execution Quality metrics
        try:
            from app.execution_quality.engine import ExecutionQualityEngine
            eq_engine = ExecutionQualityEngine(self.db)
            
            exec_order = eq_engine.record_order(
                strategy_name=signal.strategy,
                symbol=signal.symbol,
                side=signal.side.value,
                expected_price=Decimal(str(data.price)),
                expected_quantity=quantity,
                signal_time=signal_time,
                submission_time=submission_time,
                paper_order_id=order.id,
            )
            
            ack_time = submission_time + timedelta(milliseconds=5)
            fill_time = datetime.now(UTC)
            
            eq_engine.record_fill(
                execution_order_id=exec_order.id,
                fill_price=Decimal(str(execution.average_price)),
                fill_quantity=Decimal(str(execution.filled_quantity)),
                fee=Decimal(str(execution.fee)),
                fill_time=fill_time,
                ack_time=ack_time
            )
        except Exception:
            logger.warning("Paper execution-quality recording failed", exc_info=True)

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

    def close_position(self, position: PaperPosition, data: MarketData, reason: str) -> None:
        now = datetime.now(UTC)
        order = PaperOrder(
            account_id=self.account.id,
            symbol=position.symbol,
            side=OrderSide.sell,
            order_type=PaperOrderType.market,
            status=PaperOrderStatus.filled,
            requested_quantity=position.quantity,
            filled_quantity=position.quantity,
            signal={"reason": reason, "type": "exit"},
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        execution = self.simulator.execute_market(
            order_id=order.id,
            side=PaperSide.sell,
            quantity=float(position.quantity),
            data=data,
        )
        order.filled_quantity = Decimal(str(execution.filled_quantity))
        order.average_fill_price = Decimal(str(execution.average_price))
        order.fee_paid = Decimal(str(execution.fee))
        order.latency_ms = execution.latency_ms
        order.filled_at = now
        exit_price = Decimal(str(execution.average_price))
        pnl = (exit_price - position.average_entry_price) * position.quantity - Decimal(str(execution.fee))
        self.account.cash_balance += exit_price * position.quantity - Decimal(str(execution.fee))
        self.account.realized_pnl += pnl
        position.realized_pnl += pnl
        position.is_open = False
        position.closed_at = now
        self.db.add(
            PaperTrade(
                account_id=self.account.id,
                order_id=order.id,
                symbol=position.symbol,
                side=OrderSide.sell,
                price=exit_price,
                quantity=position.quantity,
                fee=Decimal(str(execution.fee)),
                realized_pnl=pnl,
            )
        )
        self._log("trade_closed", f"{position.symbol} closed: {reason}", {"pnl": str(pnl)})

        # Record Execution Quality metrics
        try:
            from app.execution_quality.engine import ExecutionQualityEngine
            eq_engine = ExecutionQualityEngine(self.db)
            
            exec_order = eq_engine.record_order(
                strategy_name="capital_preservation_v1",
                symbol=position.symbol,
                side="sell",
                expected_price=exit_price,
                expected_quantity=position.quantity,
                signal_time=now,
                submission_time=now,
            )
            
            ack_time = now + timedelta(milliseconds=5)
            fill_time = datetime.now(UTC)
            
            eq_engine.record_fill(
                execution_order_id=exec_order.id,
                fill_price=exit_price,
                fill_quantity=position.quantity,
                fee=Decimal(str(execution.fee)),
                fill_time=fill_time,
                ack_time=ack_time
            )
        except Exception:
            logger.warning("Paper execution-quality recording failed", exc_info=True)

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
            stop_loss = None
            take_profit = None
            signal_metadata = order.signal if isinstance(order.signal, dict) else {}
            atr_str = signal_metadata.get("metadata", {}).get("atr") if isinstance(signal_metadata.get("metadata"), dict) else signal_metadata.get("atr")
            if atr_str is not None:
                try:
                    atr_value = Decimal(str(atr_str))
                    # Tighter stop-loss: 2.5×ATR (was 6×ATR) for better risk management
                    stop_loss = price - atr_value * Decimal("2.5")
                    risk_per_unit = price - stop_loss
                    # Reward:Risk = 2:1 (was 1.2:1) for positive expectancy
                    take_profit = price + risk_per_unit * Decimal("2.0")
                except Exception:
                    pass
            if stop_loss is None:
                stop_loss = price * Decimal("0.85")
            if take_profit is None:
                take_profit = price * Decimal("1.15")
            self.db.add(
                PaperPosition(
                    account_id=self.account.id,
                    symbol=order.symbol,
                    quantity=quantity,
                    average_entry_price=price,
                    last_price=price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    trailing_stop=stop_loss,
                    highest_price=price,
                    breakeven_triggered=False,
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
        self.db.commit()
