from datetime import UTC, datetime
from decimal import Decimal
from time import time

from sqlalchemy.orm import Session

from app.models.entities import PaperAccount, PaperLog, PaperPosition
from app.models.enums import LogLevel, PaperBotStatus
from app.paper_trading.broker import PaperBroker
from app.paper_trading.market_data_stream import GateIOMarketDataStream
from app.paper_trading.models import BaseStrategy, MarketData, TradingSignal
from app.paper_trading.order_manager import PaperOrderManager
from app.paper_trading.portfolio import PaperPortfolio
from app.paper_trading.risk_simulator import PaperRiskSimulator
from app.repositories.trading import StrategySettingsRepository
from app.services.notifications.telegram import TelegramNotifier

import logging

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    def __init__(self, db: Session, account: PaperAccount, strategy: BaseStrategy | None = None) -> None:
        self.db = db
        self.account = account
        self.strategy = strategy or BaseStrategy()
        self.order_manager = PaperOrderManager(db, account)
        self.portfolio = PaperPortfolio(db, account)
        self.risk = PaperRiskSimulator(db, account)
        self.broker = PaperBroker(db, account)
        self.notifier = TelegramNotifier()
        self.stream: GateIOMarketDataStream | None = None

    async def start(self, symbols: list[str]) -> None:
        self.account.status = PaperBotStatus.running
        self._log("system_started", "Paper trading started")
        self.db.commit()
        logger.info("Paper trading engine starting for symbols: %s", symbols)
        self.stream = GateIOMarketDataStream(symbols)
        tick_count = 0
        last_status = time()
        async for data in self.stream.stream():
            tick_count += 1
            if time() - last_status >= 60:
                logger.info("Ticks received: %d", tick_count)
                last_status = time()
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
        if not approved:
            if reason not in ("already_in_position", "rsi_not_oversold", "below_200_ema", "not_near_20_ema", "low_volume", "excessive_24h_volatility"):
                self._log("risk_check", reason, {"signal": signal.to_dict()})
            if reason in {"daily_loss_limit_reached", "max_drawdown_reached"}:
                await self.notifier.send(f"Paper trading paused: {reason}")
            return
        self._log("risk_check", "approved", {"signal": signal.to_dict()})
        equity = self.portfolio.equity()
        price = Decimal(str(data.price))
        settings = StrategySettingsRepository(self.db).current()
        max_capital_pct = settings.max_capital_per_trade_pct if settings else Decimal("0.01")
        notional = equity * max_capital_pct
        if price > 0:
            quantity = notional / price
        else:
            quantity = Decimal("0")
        if quantity <= 0:
            return
        order = self.order_manager.execute_signal(signal, quantity, data)
        if order:
            await self.notifier.send(f"Paper trade opened: {signal.symbol} {signal.side}")

    def _handle_position_exits(self, data: MarketData) -> None:
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
                # Check if TP would also trigger on the same bar
                if position.take_profit and high >= position.take_profit:
                    self._log(
                        "sl_tp_same_bar",
                        f"{data.symbol} both SL ({position.stop_loss}) and TP ({position.take_profit}) "
                        f"triggered on same bar — SL priority (low={low}, high={high})",
                    )
                self.broker.close_position(position, data, "stop_loss")
                self._log("stop_loss_triggered", f"{data.symbol} stop loss triggered at ~{stop_price}")
            elif position.take_profit and high >= position.take_profit:
                self.broker.close_position(position, data, "take_profit")
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
