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
        # Global kill-switch: no new entries while tripped.
        if self.breaker.is_tripped():
            self._log("circuit_breaker", f"{symbol}: skipped, circuit breaker tripped")
            return

        candles = await self.client.candles(symbol)
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
        
        regime_record = regime_engine.update_regime(symbol, "1h", candles_list)
        strategy_name = self.strategy.__class__.__name__
        allowed, reason, risk_mult = regime_engine.should_trade(strategy_name, symbol)
        
        if not allowed:
            self._log("regime_filter", f"{symbol} trade blocked by regime: {reason}")
            return

        # Strategy Health Filter
        from app.strategy_health.engine import StrategyHealthEngine
        health_engine = StrategyHealthEngine(self.db)
        health_status = health_engine.update_health(strategy_name)
        
        if health_status["state"] in ("PAUSED", "DISABLED"):
            self._log("health_filter", f"{symbol} trade blocked: strategy health is {health_status['state']}")
            return

        decision = self.risk.approve_entry(equity, signal.entry_price, signal.atr_value)
        if not decision.allowed:
            self._log("risk", f"{symbol}: {decision.reason}")
            return

        # Scale position quantity by both regime and health risk multipliers
        health_mult = health_status["risk_multiplier"]
        final_quantity = decision.quantity * risk_mult * health_mult
        if final_quantity <= 0:
            self._log("risk_filter", f"{symbol} trade quantity scaled to zero by risk filters (regime: {risk_mult}x, health: {health_mult}x)")
            return


        response = await self.client.place_market_order(symbol, "buy", final_quantity)
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
            quantity=decision.quantity,
            raw_response=json.dumps(response),
        )
        self.db.add(order)
        self.db.commit()
        await self.notifier.send(f"Opened {symbol}: qty={decision.quantity} entry={signal.entry_price}")

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
        response = await self.client.place_market_order(position.symbol, "sell", position.quantity)
        exit_price = Decimal(str(response.get("avg_deal_price") or position.entry_price))
        pnl = (exit_price - position.entry_price) * position.quantity
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
        trade = Trade(
            order_id=None,
            symbol=position.symbol,
            side=OrderSide.sell,
            price=exit_price,
            quantity=position.quantity,
            realized_pnl=pnl,
        )
        self.db.add_all([order, trade])
        self.db.commit()
        self.db.refresh(order)
        await self.notifier.send(f"Closed {position.symbol}: {reason}, pnl={pnl}")
        return order

    def _update_trailing_stop(self, position: Position, price: Decimal) -> None:
        if position.trailing_stop and price <= position.trailing_stop:
            return
        new_stop = price * Decimal("0.99")
        if new_stop > position.stop_loss:
            position.trailing_stop = new_stop
            position.stop_loss = new_stop
            self.db.commit()

    def _log(self, source: str, message: str, level: LogLevel = LogLevel.info) -> None:
        self.db.add(SystemLog(level=level, source=source, message=message))
        self.db.commit()
