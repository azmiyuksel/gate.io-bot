import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from time import time

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import PaperAccount, PaperLog, PaperPosition
from app.models.enums import LogLevel, PaperBotStatus
from app.paper_trading.broker import PaperBroker
from app.paper_trading.market_data_stream import GateIOMarketDataStream
from app.paper_trading.models import BaseStrategy, MarketData, TradingSignal
from app.paper_trading.order_manager import PaperOrderManager
from app.paper_trading.portfolio import PaperPortfolio
from app.paper_trading.risk_simulator import PaperRiskSimulator
from app.repositories.trading import StrategySettingsRepository
from app.services.exchange.gateio import GateIOClient
from app.services.notifications.telegram import TelegramNotifier

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
        self._client: GateIOClient | None = None
        self._running = False

    async def start(self, symbols: list[str]) -> None:
        self.account.status = PaperBotStatus.running
        self._log("system_started", "Paper trading started")
        self.db.commit()
        logger.info("Paper trading engine starting for symbols: %s", symbols)
        self._running = True
        self.stream = GateIOMarketDataStream(symbols)
        self._client = GateIOClient()
        try:
            # Two concurrent loops: ticks drive mark-to-market and stop/TP exits,
            # while a periodic loop evaluates entries on real OHLC candles (the
            # same data the live engine uses) so signals are meaningful.
            await asyncio.gather(
                self._run_tick_loop(),
                self._run_entry_loop(symbols),
            )
        finally:
            if self._client is not None:
                await self._client.close()

    async def _run_tick_loop(self) -> None:
        tick_count = 0
        tick_per_symbol: dict[str, int] = {}
        last_status = time()
        async for data in self.stream.stream():
            tick_per_symbol[data.symbol] = tick_per_symbol.get(data.symbol, 0) + 1
            tick_count += 1
            if time() - last_status >= 60:
                logger.info("Ticks received: %d, per symbol: %s", tick_count, tick_per_symbol)
                last_status = time()
            await self.on_tick(data)

    async def _run_entry_loop(self, symbols: list[str]) -> None:
        """Evaluate entries periodically on real candles (independent of ticks)."""
        settings = get_settings()
        while self._running:
            # Honour pause/stop toggled via the API (different DB session).
            try:
                self.db.refresh(self.account)
            except Exception:
                pass
            if self.account.status == PaperBotStatus.running:
                await self._evaluate_entries(symbols, settings)
            await asyncio.sleep(max(int(settings.paper_eval_interval_seconds), 1))

    async def _evaluate_entries(self, symbols: list[str], settings) -> None:
        for symbol in symbols:
            try:
                candles = await self._client.candles(
                    symbol,
                    interval=settings.market_data_interval,
                    limit=settings.candle_history_limit,
                )
            except Exception as exc:
                logger.warning("paper entry: candle fetch failed for %s: %s", symbol, exc)
                continue
            if not candles:
                continue
            signal = self.strategy.evaluate_real_candles(symbol, candles)
            if signal is None:
                continue
            latest = candles[-1]
            # Build a MarketData snapshot from the latest REAL candle (proper OHLC),
            # so execution simulation and risk checks see correct bar values.
            data = MarketData(
                symbol=symbol,
                timestamp=datetime.now(UTC),
                price=float(latest["close"]),
                volume=float(latest.get("volume") or 0),
                high=float(latest["high"]),
                low=float(latest["low"]),
            )
            await self.execute_signal(signal, data)

    def stop(self) -> None:
        self._running = False
        self.account.status = PaperBotStatus.stopped
        if self.stream:
            self.stream.stop()
        self._log("system_stopped", "Paper trading stopped")
        self.db.commit()

    async def on_tick(self, data: MarketData) -> None:
        # Ticks only maintain mark-to-market and trigger stop/TP exits. Entries are
        # evaluated separately on real candles in the entry loop.
        self.portfolio.mark_price(data.symbol, Decimal(str(data.price)))
        self._handle_position_exits(data)
        self.portfolio.record_equity()

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
        # Stream ticks carry no intra-bar range, so evaluate stops/TPs against the
        # live tick price. With frequent ticks this catches level breaches promptly;
        # the stop is checked before the take-profit to protect capital first.
        price = Decimal(str(data.price))
        for position in positions:
            if position.stop_loss and price <= position.stop_loss:
                self.broker.close_position(position, data, "stop_loss")
                self._log("stop_loss_triggered", f"{data.symbol} stop loss triggered at ~{price}")
            elif position.take_profit and price >= position.take_profit:
                self.broker.close_position(position, data, "take_profit")
                self._log("take_profit_triggered", f"{data.symbol} take profit triggered at ~{price}")

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
