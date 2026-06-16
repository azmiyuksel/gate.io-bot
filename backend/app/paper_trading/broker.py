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
        from app.core.config import get_settings

        self.db = db
        self.account = account
        if simulator is None:
            s = get_settings()
            simulator = ExecutionSimulator(maker_fee=s.paper_maker_fee, taker_fee=s.paper_taker_fee)
        self.simulator = simulator

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

    def _stop_tp_params(self) -> tuple[Decimal, Decimal]:
        """(ATR stop multiplier, take-profit reward:risk) from config — shared by
        long/short opens and by the engine's position sizing so the stop the trade
        is sized against is the stop actually placed."""
        from app.core.config import get_settings

        s = get_settings()
        return Decimal(str(s.paper_atr_stop_multiplier)), Decimal(str(s.paper_tp_rr))

    def _fits_free_margin(self, notional: Decimal) -> bool:
        """A new long's notional must fit within free margin (equity * leverage)
        minus the notional already committed to open positions."""
        from app.core.config import get_settings

        from app.paper_trading.portfolio import PaperPortfolio

        portfolio = PaperPortfolio(self.db, self.account)
        equity = portfolio.equity()
        if equity <= 0:
            return False
        leverage = Decimal(str(get_settings().paper_leverage))
        used = sum(p.quantity * p.last_price for p in portfolio.open_positions())
        return (used + notional) <= equity * leverage

    def _funding_cost(self, position: PaperPosition, close_qty: Decimal, exit_time: datetime) -> Decimal:
        """Conservative financing carry on the closed notional over the holding
        period. Disabled when ``funding_cost_enabled`` is off."""
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.funding_cost_enabled or settings.funding_daily_rate_pct <= 0:
            return Decimal("0")
        opened = position.opened_at
        if opened is None:
            return Decimal("0")
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=UTC)
        held_seconds = (exit_time - opened).total_seconds()
        if held_seconds <= 0:
            return Decimal("0")
        held_days = Decimal(str(held_seconds / 86_400.0))
        rate = Decimal(str(settings.funding_daily_rate_pct))
        return position.average_entry_price * close_qty * rate * held_days

    def close_position(self, position: PaperPosition, data: MarketData, reason: str, quantity: Decimal | None = None) -> None:
        now = datetime.now(UTC)
        close_qty = quantity if quantity is not None and quantity < position.quantity else position.quantity
        is_short = position.side == "sell"
        close_side = OrderSide.buy if is_short else OrderSide.sell
        exit_price = Decimal(str(data.price))
        exit_sim_side = PaperSide.buy if is_short else PaperSide.sell

        order = PaperOrder(
            account_id=self.account.id,
            symbol=position.symbol,
            side=close_side,
            order_type=PaperOrderType.market,
            status=PaperOrderStatus.filled,
            requested_quantity=close_qty,
            filled_quantity=close_qty,
            signal={"reason": reason, "type": "partial" if close_qty < position.quantity else "exit"},
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        execution = self.simulator.execute_market(
            order_id=order.id,
            side=exit_sim_side,
            quantity=float(close_qty),
            data=data,
        )
        order.filled_quantity = Decimal(str(execution.filled_quantity))
        order.average_fill_price = Decimal(str(execution.average_price))
        order.fee_paid = Decimal(str(execution.fee))
        order.latency_ms = execution.latency_ms
        order.filled_at = now
        if is_short:
            pnl = (position.average_entry_price - exit_price) * close_qty - Decimal(str(execution.fee))
        else:
            pnl = (exit_price - position.average_entry_price) * close_qty - Decimal(str(execution.fee))
        # Financing carry (perp funding / spot borrow): a multi-day hold is not
        # cost-free. Deduct a conservative daily cost on notional so simulated PnL
        # is not overstated relative to live trading.
        pnl -= self._funding_cost(position, close_qty, now)
        self.account.cash_balance += position.average_entry_price * close_qty + pnl
        self.account.realized_pnl += pnl
        position.realized_pnl += pnl

        if close_qty >= position.quantity:
            position.is_open = False
            position.closed_at = now
        else:
            position.quantity -= close_qty

        self.db.add(
            PaperTrade(
                account_id=self.account.id,
                order_id=order.id,
                symbol=position.symbol,
                side=close_side,
                price=exit_price,
                quantity=close_qty,
                fee=Decimal(str(execution.fee)),
                realized_pnl=pnl,
                exit_reason=reason,
            )
        )
        self._log("trade_closed", f"{position.symbol} {'partial ' if close_qty < position.quantity else ''}closed: {reason}", {"pnl": str(pnl)})

        try:
            from app.execution_quality.engine import ExecutionQualityEngine
            eq_engine = ExecutionQualityEngine(self.db)
            exec_order = eq_engine.record_order(
                strategy_name="capital_preservation_v1",
                symbol=position.symbol,
                side=close_side.value if isinstance(close_side, OrderSide) else close_side,
                expected_price=exit_price,
                expected_quantity=close_qty,
                signal_time=now,
                submission_time=now,
            )
            ack_time = now + timedelta(milliseconds=5)
            fill_time = datetime.now(UTC)
            eq_engine.record_fill(
                execution_order_id=exec_order.id,
                fill_price=exit_price,
                fill_quantity=close_qty,
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

        # Check if there's an existing open SHORT position to close (buy to cover)
        existing_short = (
            self.db.query(PaperPosition)
            .filter(
                PaperPosition.account_id == self.account.id,
                PaperPosition.symbol == order.symbol,
                PaperPosition.is_open.is_(True),
                PaperPosition.side == "sell",
            )
            .first()
        )
        if existing_short:
            cover_qty = min(quantity, existing_short.quantity)
            self.close_position(
                existing_short,
                MarketData(order.symbol, datetime.now(UTC), float(price)),
                "signal_cover",
                quantity=cover_qty,
            )
            return

        # Open or add to a LONG position. Futures margin: a long may use leverage,
        # so cash is allowed to go negative (borrowed funds) as long as the trade
        # fits within free margin (equity * leverage). Equity stays correct because
        # the position's market value is added back in PaperPortfolio.equity().
        if not self._fits_free_margin(quantity * price):
            order.status = PaperOrderStatus.rejected
            self._log("order_rejected", "exceeds free margin (leverage cap)")
            return
        self.account.cash_balance -= total_cost
        existing = (
            self.db.query(PaperPosition)
            .filter(
                PaperPosition.account_id == self.account.id,
                PaperPosition.symbol == order.symbol,
                PaperPosition.is_open.is_(True),
                PaperPosition.side == "buy",
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
                    stop_mult, tp_rr = self._stop_tp_params()
                    stop_loss = price - atr_value * stop_mult
                    risk_per_unit = price - stop_loss
                    take_profit = price + risk_per_unit * tp_rr
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
                    side="buy",
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
        quantity = Decimal(str(execution.filled_quantity))
        price = Decimal(str(execution.average_price))
        fee = Decimal(str(execution.fee))

        # Check if there's an existing open LONG position to close
        existing_long = (
            self.db.query(PaperPosition)
            .filter(
                PaperPosition.account_id == self.account.id,
                PaperPosition.symbol == order.symbol,
                PaperPosition.is_open.is_(True),
                PaperPosition.side == "buy",
            )
            .first()
        )
        if existing_long:
            self.close_position(
                existing_long,
                MarketData(order.symbol, datetime.now(UTC), float(price)),
                "signal_sell",
            )
            return

        # Open a SHORT position (sell to open). Margin guard mirrors the long side:
        # the short's notional must fit within free margin (equity * leverage).
        if not self._fits_free_margin(quantity * price):
            order.status = PaperOrderStatus.rejected
            self._log("order_rejected", "exceeds free margin (leverage cap)")
            return
        # For short: cash increases by sale proceeds minus fee
        self.account.cash_balance += quantity * price - fee
        stop_loss = None
        take_profit = None
        signal_metadata = order.signal if isinstance(order.signal, dict) else {}
        atr_str = signal_metadata.get("metadata", {}).get("atr") if isinstance(signal_metadata.get("metadata"), dict) else signal_metadata.get("atr")
        if atr_str is not None:
            try:
                atr_value = Decimal(str(atr_str))
                stop_mult, tp_rr = self._stop_tp_params()
                # For short: stop is above entry, target is below entry
                stop_loss = price + atr_value * stop_mult
                risk_per_unit = stop_loss - price
                take_profit = price - risk_per_unit * tp_rr
            except Exception:
                pass
        if stop_loss is None:
            stop_loss = price * Decimal("1.15")
        if take_profit is None:
            take_profit = price * Decimal("0.85")
        self.db.add(
            PaperPosition(
                account_id=self.account.id,
                symbol=order.symbol,
                side="sell",
                quantity=quantity,
                average_entry_price=price,
                last_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                trailing_stop=stop_loss,
                highest_price=None,
                breakeven_triggered=False,
            )
        )

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
