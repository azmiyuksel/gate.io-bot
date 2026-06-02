import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import Order, Position, SystemLog, Trade
from app.models.enums import LogLevel, OrderSide, OrderStatus, PositionStatus
from app.repositories.trading import OrderRepository, PositionRepository
from app.services.exchange.gateio import GateIOClient
from app.services.notifications.telegram import TelegramNotifier
from app.services.risk.circuit_breaker import CircuitBreaker
from app.services.risk.manager import RiskManager
from app.services.strategy.signals import CapitalPreservationStrategy


class TradingEngine:
    def __init__(self, db: Session, client: GateIOClient) -> None:
        self.db = db
        self.client = client
        self.strategy = CapitalPreservationStrategy()
        self.risk = RiskManager(db)
        self.breaker = CircuitBreaker(db)
        self.positions = PositionRepository(db)
        self.orders = OrderRepository(db)
        self.notifier = TelegramNotifier()

    async def scan_symbol(self, symbol: str, equity: Decimal) -> None:
        signal_time = datetime.now(UTC)
        # Global kill-switch: no new entries while tripped.
        if self.breaker.is_tripped():
            self._log("circuit_breaker", f"{symbol}: skipped, circuit breaker tripped")
            return

        candles = await self.client.candles(symbol)

        # Market Data Quality gate: run the feed through the quality pipeline and
        # block trading on unreliable data, de-risk on degraded data.
        from app.core.config import get_settings
        from app.market_data_quality.engine import MarketDataQualityEngine
        from app.market_data_quality.models import DataTradeStatus

        mdq_result = MarketDataQualityEngine(self.db).ingest(candles, symbol, "1h", source="gateio")
        data_status = mdq_result.trade_status
        if data_status == DataTradeStatus.invalid and get_settings().mdq_pause_on_invalid:
            self._log(
                "data_quality",
                f"{symbol}: trading paused, data INVALID (health={mdq_result.health.score})",
            )
            return
        data_risk_mult = Decimal("0.5") if data_status == DataTradeStatus.degraded else Decimal("1")

        signal = self.strategy.evaluate(candles)
        if not signal.should_buy or signal.entry_price is None or signal.atr_value is None:
            self._log("strategy", f"{symbol}: {signal.reason}")
            return

        # Market Regime Detection Filter
        from app.market_regime.engine import MarketRegimeEngine
        regime_engine = MarketRegimeEngine(self.db)
        
        # Convert exchange candles to list of dicts for feature calculation
        candles_list = [
            {
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c["volume"]),
                "timestamp": c["timestamp"]
            }
            for c in candles
        ]
        
        regime_engine.update_regime(symbol, "1h", candles_list)
        strategy_name = self.strategy.name
        allowed, reason, risk_mult = regime_engine.should_trade(strategy_name, symbol)
        
        if not allowed:
            self._log("regime_filter", f"{symbol} trade blocked by regime: {reason}")
            return

        # Strategy Health Filter
        from app.strategy_health.engine import StrategyHealthEngine
        health_engine = StrategyHealthEngine(self.db)
        health_status = health_engine.update_health(strategy_name) or {}

        health_state = health_status.get("state")
        if health_state in ("PAUSED", "DISABLED"):
            self._log("health_filter", f"{symbol} trade blocked: strategy health is {health_state}")
            return

        decision = self.risk.approve_entry(equity, signal.entry_price, signal.atr_value)
        if not decision.allowed:
            self._log("risk", f"{symbol}: {decision.reason}")
            return

        # Scale position quantity by regime, health and data-quality risk multipliers
        health_mult = Decimal(str(health_status.get("risk_multiplier", 1)))
        final_quantity = decision.quantity * risk_mult * health_mult * data_risk_mult
        if final_quantity <= 0:
            self._log("risk_filter", f"{symbol} trade quantity scaled to zero by risk filters (regime: {risk_mult}x, health: {health_mult}x, data: {data_risk_mult}x)")
            return

        submission_time = datetime.now(UTC)
        response = await self.client.place_market_order(symbol, "buy", final_quantity)
        ack_time = datetime.now(UTC)
        position = Position(
            symbol=symbol,
            entry_price=signal.entry_price,
            quantity=final_quantity,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
        )
        self.db.add(position)
        self.db.flush()
        order = Order(
            exchange_order_id=str(response.get("id")),
            position_id=position.id,
            symbol=symbol,
            side=OrderSide.buy,
            status=OrderStatus.open,
            price=signal.entry_price,
            quantity=final_quantity,
            raw_response=json.dumps(response),
        )
        self.db.add(order)
        try:
            self.db.commit()
        except Exception:
            # The exchange order is already live; roll back the local write so the
            # session is consistent and let reconciliation recover the order state.
            self.db.rollback()
            self._log(
                "trade_persist_error",
                f"{symbol}: failed to persist order {response.get('id')}, rolled back",
                LogLevel.error,
            )
            raise
        self.db.refresh(order)

        # Record Execution Quality metrics
        try:
            from app.execution_quality.engine import ExecutionQualityEngine
            eq_engine = ExecutionQualityEngine(self.db)
            exec_order = eq_engine.record_order(
                strategy_name=strategy_name,
                symbol=symbol,
                side="buy",
                expected_price=signal.entry_price,
                expected_quantity=final_quantity,
                signal_time=signal_time,
                submission_time=submission_time,
                order_id=order.id,
            )
            fill_price = Decimal(str(response.get("avg_deal_price") or signal.entry_price))
            fill_qty = Decimal(str(response.get("filled_total") or final_quantity))
            fee = Decimal(str(response.get("fee") or 0.0))
            
            eq_engine.record_fill(
                execution_order_id=exec_order.id,
                fill_price=fill_price,
                fill_quantity=fill_qty,
                fee=fee,
                fill_time=datetime.now(UTC),
                ack_time=ack_time
            )
        except Exception as e:
            # Best-effort audit metric; clear any partial state so the session
            # stays usable for the rest of the cycle.
            self.db.rollback()
            self._log("execution_quality_error", f"Failed to record execution quality: {e}")

        await self.notifier.send(f"Opened {symbol}: qty={final_quantity} entry={signal.entry_price}")


    async def manage_open_positions(self) -> None:
        for position in self.positions.open_positions():
            candles = await self.client.candles(position.symbol, limit=2)
            price = Decimal(str(candles[-1]["close"]))
            if price <= position.stop_loss:
                await self.close_position(position, "stop_loss")
            elif price >= position.take_profit:
                await self.close_position(position, "take_profit")
            else:
                self._update_trailing_stop(position, price)

    async def close_position(self, position: Position, reason: str) -> Order:
        signal_time = datetime.now(UTC)
        from app.execution_quality.engine import ExecutionQualityEngine
        eq_engine = ExecutionQualityEngine(self.db)
        
        submission_time = datetime.now(UTC)
        response = await self.client.place_market_order(position.symbol, "sell", position.quantity)
        ack_time = datetime.now(UTC)
        
        exit_price = Decimal(str(response.get("avg_deal_price") or position.entry_price))
        # Exit fee is reported by the exchange (quote currency for a spot sell).
        fee = Decimal(str(response.get("fee") or 0))
        # Realized PnL must be net of fees, otherwise reported PnL is systematically optimistic.
        pnl = (exit_price - position.entry_price) * position.quantity - fee
        position.status = PositionStatus.closed
        position.closed_at = datetime.now(UTC)
        position.realized_pnl = pnl
        order = Order(
            exchange_order_id=str(response.get("id")),
            position_id=position.id,
            symbol=position.symbol,
            side=OrderSide.sell,
            status=OrderStatus.open,
            price=exit_price,
            quantity=position.quantity,
            raw_response=json.dumps(response),
        )
        self.db.add(order)
        self.db.flush()  # assign order.id so the trade can reference it
        trade = Trade(
            order_id=order.id,
            symbol=position.symbol,
            side=OrderSide.sell,
            price=exit_price,
            quantity=position.quantity,
            fee=fee,
            realized_pnl=pnl,
        )
        self.db.add(trade)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            self._log(
                "trade_persist_error",
                f"{position.symbol}: failed to persist close {response.get('id')}, rolled back",
                LogLevel.error,
            )
            raise
        self.db.refresh(order)

        # Record Execution Quality metrics
        try:
            strategy_name = self.strategy.name
            exec_order = eq_engine.record_order(
                strategy_name=strategy_name,
                symbol=position.symbol,
                side="sell",
                expected_price=exit_price,
                expected_quantity=position.quantity,
                signal_time=signal_time,
                submission_time=submission_time,
                order_id=order.id,
            )
            fill_qty = Decimal(str(response.get("filled_total") or position.quantity))

            eq_engine.record_fill(
                execution_order_id=exec_order.id,
                fill_price=exit_price,
                fill_quantity=fill_qty,
                fee=fee,
                fill_time=datetime.now(UTC),
                ack_time=ack_time
            )
        except Exception as e:
            self.db.rollback()
            self._log("execution_quality_error", f"Failed to record execution quality on close: {e}")

        await self.notifier.send(f"Closed {position.symbol}: {reason}, pnl={pnl}")
        return order

    def _update_trailing_stop(self, position: Position, price: Decimal) -> None:
        if position.trailing_stop and price <= position.trailing_stop:
            return
        new_stop = price * Decimal("0.99")
        if new_stop > position.stop_loss:
            position.stop_loss = new_stop
            self.db.commit()

    def _log(self, source: str, message: str, level: LogLevel = LogLevel.info) -> None:
        self.db.add(SystemLog(level=level, source=source, message=message))
        self.db.commit()

