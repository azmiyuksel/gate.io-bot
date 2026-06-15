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
            # Auto-resume from PAUSED after cooldown if risk limits recovered
            if self.account.status == PaperBotStatus.paused:
                self.risk.maybe_auto_resume()
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
                # Surface fetch failures to the dashboard instead of failing silently
                # (a worker with no outbound network would otherwise look idle).
                logger.warning("paper entry: candle fetch failed for %s: %s", symbol, exc)
                self._log(
                    "entry_skipped",
                    f"{symbol}: candle_fetch_failed ({exc})",
                    {"symbol": symbol, "reason": "candle_fetch_failed"},
                )
                continue
            if not candles:
                self._log(
                    "entry_skipped",
                    f"{symbol}: no_candles",
                    {"symbol": symbol, "reason": "no_candles"},
                )
                continue
            signal = self.strategy.evaluate_real_candles(symbol, candles)
            if signal is None:
                reason = getattr(self.strategy, "last_reason", "") or "no_signal"
                self._log("entry_skipped", f"{symbol}: {reason}", {"symbol": symbol, "reason": reason})
                continue

            # Multi-timeframe confirmation: check HTF trend alignment
            if getattr(settings, "strategy_mtf_enabled", False):
                try:
                    htf_candles = await self._client.candles(
                        symbol,
                        interval=settings.strategy_mtf_interval,
                        limit=50,
                    )
                    if htf_candles and len(htf_candles) >= 50:
                        from app.services.strategy.indicators import ema as calc_ema
                        htf_closes = [Decimal(str(c["close"])) for c in htf_candles]
                        htf_ema200 = calc_ema(htf_closes, 50)
                        htf_last = htf_closes[-1]
                        direction = signal.metadata.get("direction") if signal.metadata else "long"
                        if direction == "long" and htf_last < htf_ema200:
                            self._log("entry_skipped", f"{symbol}: htf_trend_mismatch (long but 4h below EMA50)",
                                      {"symbol": symbol, "reason": "htf_trend_mismatch"})
                            continue
                        if direction == "short" and htf_last > htf_ema200:
                            self._log("entry_skipped", f"{symbol}: htf_trend_mismatch (short but 4h above EMA50)",
                                      {"symbol": symbol, "reason": "htf_trend_mismatch"})
                            continue
                except Exception:
                    pass  # MTF check is advisory; proceed if it fails

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
            self._log("risk_check", f"{signal.symbol}: {reason}", {"symbol": signal.symbol, "reason": reason})
            if reason in {"daily_loss_limit_reached", "max_drawdown_reached"}:
                await self.notifier.send(f"Paper trading paused: {reason}")
            return
        self._log("risk_check", f"{signal.symbol}: approved", {"symbol": signal.symbol, "reason": "approved"})
        equity = self.portfolio.equity()
        price = Decimal(str(data.price))
        config = get_settings()
        settings = StrategySettingsRepository(self.db).current()
        max_capital_pct = settings.max_capital_per_trade_pct if settings else Decimal("0.01")
        max_risk_pct = Decimal(str(config.max_risk_per_trade_pct))

        # Risk-constrained position sizing: the risk-based quantity (sized so loss-to-stop
        # equals max_risk_pct of equity) is bound above by a notional cap (max_capital_pct).
        # This means risk-based sizing constrains rather than drives the final position size.
        atr_str = signal.metadata.get("atr") if signal.metadata else None
        if atr_str and config.risk_based_sizing_enabled:
            try:
                atr_value = Decimal(str(atr_str))
                stop_distance = atr_value * Decimal("2.5")  # matches broker stop-loss
                if stop_distance > 0:
                    max_loss_per_trade = equity * max_risk_pct
                    risk_based_qty = max_loss_per_trade / stop_distance
                    # Cap at max notional
                    max_notional = equity * max_capital_pct
                    notional_capped_qty = max_notional / price if price > 0 else Decimal("0")
                    quantity = min(risk_based_qty, notional_capped_qty)
                else:
                    quantity = (equity * max_capital_pct) / price if price > 0 else Decimal("0")
            except Exception:
                quantity = (equity * max_capital_pct) / price if price > 0 else Decimal("0")
        else:
            notional = equity * max_capital_pct
            quantity = notional / price if price > 0 else Decimal("0")

        if quantity <= 0:
            return

        # Kelly-optimal fraction: scale position by edge quality
        # kelly_f = win_rate - (1 - win_rate) / payoff_ratio
        # Clamped to [0.25, 1.0] of base size to prevent ruin
        try:
            from app.paper_trading.metrics import PaperMetrics
            metrics = PaperMetrics(self.db, self.account.id).summary()
            wr = metrics.get("win_rate_rolling_100", 0)
            # Estimate payoff from recent equity returns
            if wr > 0 and wr < 1:
                kelly_f = wr - (1 - wr) / max(wr, 0.01)
                scale = max(Decimal("0.25"), min(Decimal("1.0"), Decimal(str(max(kelly_f, 0.10)))))
                quantity = quantity * scale
        except Exception:
            pass

        order = self.order_manager.execute_signal(signal, quantity, data)
        if order:
            await self.notifier.send(f"Paper trade opened: {signal.symbol} {signal.side}")

    def _handle_position_exits(self, data: MarketData) -> None:
        positions = (
            self.db.query(PaperPosition)
            .filter(PaperPosition.account_id == self.account.id, PaperPosition.symbol == data.symbol, PaperPosition.is_open.is_(True))
            .all()
        )
        price = Decimal(str(data.price))
        settings = get_settings()
        breakeven_trigger = Decimal(str(settings.breakeven_stop_trigger_pct))
        trailing_pct = Decimal(str(settings.strategy_trailing_stop_pct))

        for position in positions:
            is_short = position.side == "sell"

            # For short positions, exit logic is mirrored:
            # - stop_loss is ABOVE entry (price going up is bad)
            # - take_profit is BELOW entry (price going down is good)
            # - trailing stop ratchets DOWNWARD
            # - breakeven triggered when profit_pct >= trigger (price moved down)

            # Update highest/lowest price seen for trailing stop
            if is_short:
                if position.highest_price is None or price < position.highest_price:
                    position.highest_price = price
            else:
                if position.highest_price is None or price > position.highest_price:
                    position.highest_price = price

            # Breakeven stop
            if not position.breakeven_triggered and position.average_entry_price > 0:
                if is_short:
                    profit_pct = (position.average_entry_price - price) / position.average_entry_price
                else:
                    profit_pct = (price - position.average_entry_price) / position.average_entry_price
                if profit_pct >= breakeven_trigger:
                    round_trip_fee = position.average_entry_price * Decimal("0.002")
                    if is_short:
                        position.stop_loss = position.average_entry_price - round_trip_fee
                    else:
                        position.stop_loss = position.average_entry_price + round_trip_fee
                    position.breakeven_triggered = True
                    self._log("breakeven_stop", f"{data.symbol} stop moved to breakeven (incl. fees)")

            # Trailing stop: ratchet as price moves favorably
            if position.breakeven_triggered and position.highest_price and trailing_pct > 0:
                if is_short:
                    trailing_stop = position.highest_price * (Decimal("1") + trailing_pct)
                    if position.trailing_stop is None or trailing_stop < position.trailing_stop:
                        position.trailing_stop = trailing_stop
                        position.stop_loss = trailing_stop
                else:
                    trailing_stop = position.highest_price * (Decimal("1") - trailing_pct)
                    if position.trailing_stop is None or trailing_stop > position.trailing_stop:
                        position.trailing_stop = trailing_stop
                        position.stop_loss = trailing_stop

            # Dynamic stop-loss: ratchet tighter as price moves favorably
            # Uses 2.5% of current price as stop distance, only tightens (never loosens)
            if not position.breakeven_triggered and position.stop_loss:
                try:
                    stop_distance = price * Decimal("0.025")
                    if is_short:
                        new_stop = price + stop_distance
                        if new_stop < position.stop_loss:
                            position.stop_loss = new_stop
                    else:
                        new_stop = price - stop_distance
                        if new_stop > position.stop_loss:
                            position.stop_loss = new_stop
                except Exception:
                    pass

            # Check exits: stop-loss checked before take-profit (capital protection first)
            if is_short:
                if position.stop_loss and price >= position.stop_loss:
                    reason = "trailing_stop" if position.breakeven_triggered else "stop_loss"
                    self.broker.close_position(position, data, reason)
                    self._log(f"{reason}_triggered", f"{data.symbol} {reason} triggered at ~{price}")
                elif position.take_profit and price <= position.take_profit:
                    self.broker.close_position(position, data, "take_profit")
                    self._log("take_profit_triggered", f"{data.symbol} take profit triggered at ~{price}")
            else:
                if position.stop_loss and price <= position.stop_loss:
                    reason = "trailing_stop" if position.breakeven_triggered else "stop_loss"
                    self.broker.close_position(position, data, reason)
                    self._log(f"{reason}_triggered", f"{data.symbol} {reason} triggered at ~{price}")
                elif position.take_profit and price >= position.take_profit:
                    self.broker.close_position(position, data, "take_profit")
                    self._log("take_profit_triggered", f"{data.symbol} take profit triggered at ~{price}")

    def _log(self, event: str, message: str, payload: dict | None = None) -> None:
        # Commit immediately so diagnostics persist even when no ticks are flowing
        # (e.g. the WS feed is down but REST entry evaluation still runs).
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
        self.db.commit()
