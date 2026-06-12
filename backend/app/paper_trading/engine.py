from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import PaperAccount, PaperLog, PaperPosition
from app.models.enums import LogLevel, PaperBotStatus
from app.paper_trading.market_data_stream import GateIOMarketDataStream
from app.paper_trading.models import BaseStrategy, MarketData, TradingSignal
from app.paper_trading.order_manager import PaperOrderManager
from app.paper_trading.portfolio import PaperPortfolio
from app.paper_trading.risk_simulator import PaperRiskSimulator
from app.services.notifications.telegram import TelegramNotifier


class PaperTradingEngine:
    def __init__(self, db: Session, account: PaperAccount, strategy: BaseStrategy | None = None) -> None:
        self.db = db
        self.account = account
        self.strategy = strategy or BaseStrategy()
        self.order_manager = PaperOrderManager(db, account)
        self.portfolio = PaperPortfolio(db, account)
        self.risk = PaperRiskSimulator(db, account)
        self.notifier = TelegramNotifier()
        self.stream: GateIOMarketDataStream | None = None

    async def start(self, symbols: list[str]) -> None:
        self.account.status = PaperBotStatus.running
        self._log("system_started", "Paper trading started")
        self.db.commit()
        self.stream = GateIOMarketDataStream(symbols)
        async for data in self.stream.stream():
            await self.on_tick(data)

    def stop(self) -> None:
        self.account.status = PaperBotStatus.stopped
        if self.stream:
            self.stream.stop()
        self._log("system_stopped", "Paper trading stopped")
        self.db.commit()

    async def on_tick(self, data: MarketData) -> None:
        self.portfolio.mark_price(data.symbol, Decimal(str(data.price)))
        self._handle_position_exits(data)
        self.strategy.on_market_data(data)
        signal = self.strategy.generate_signal()
        if signal:
            await self.execute_signal(signal, data)
        self.portfolio.record_equity()

    async def on_candle(self, candle: MarketData) -> None:
        await self.on_tick(candle)

    async def execute_signal(self, signal: TradingSignal, data: MarketData) -> None:
        approved, reason = self.risk.approve_signal(signal, data)
        self._log("risk_check", reason, {"signal": signal.__dict__})
        if not approved:
            if reason in {"daily_loss_limit_reached", "max_drawdown_reached"}:
                await self.notifier.send(f"Paper trading paused: {reason}")
            return
        equity = self.portfolio.equity()
        quantity = Decimal(str(max(signal.strength, 0) * float(equity) * 0.01 / data.price))
        order = self.order_manager.execute_signal(signal, quantity, data)
        if order:
            await self.notifier.send(f"Paper trade opened: {signal.symbol} {signal.side}")

    def _handle_position_exits(self, data: MarketData) -> None:
        from app.paper_trading.broker import PaperBroker

        broker = PaperBroker(self.db, self.account)
        positions = (
            self.db.query(PaperPosition)
            .filter(PaperPosition.account_id == self.account.id, PaperPosition.symbol == data.symbol, PaperPosition.is_open.is_(True))
            .all()
        )
        for position in positions:
            price = Decimal(str(data.price))
            low = Decimal(str(data.low)) if data.low is not None else price
            high = Decimal(str(data.high)) if data.high is not None else price
            # Use low for stop-loss check to simulate gap-down / intra-bar stop trigger.
            # Use high for take-profit check to simulate intra-bar TP trigger.
            if position.stop_loss and low <= position.stop_loss:
                stop_price = min(position.stop_loss, price)
                broker.close_position(position, data, "stop_loss")
                self._log("stop_loss_triggered", f"{data.symbol} stop loss triggered at ~{stop_price}")
            elif position.take_profit and high >= position.take_profit:
                broker.close_position(position, data, "take_profit")
                self._log("take_profit_triggered", f"{data.symbol} take profit triggered")

    def _log(self, event: str, message: str, payload: dict | None = None) -> None:
        self.db.add(
            PaperLog(
                account_id=self.account.id,
                level=LogLevel.info,
                event=event,
                message=message,
                payload=payload or {},
                created_at=datetime.now(UTC),
            )
        )
