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
from app.paper_trading.models import BaseStrategy, MarketData, PaperSide, TradingSignal
from app.paper_trading.order_manager import PaperOrderManager
from app.paper_trading.portfolio import PaperPortfolio
from app.paper_trading.risk_simulator import PaperRiskSimulator
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
        self._lock = asyncio.Lock()
        self._last_risk_log_ts: float = 0
        self._log_batch: list = []
        self._last_log_commit = time()

    async def start(self, symbols: list[str]) -> None:
        if self.account.status != PaperBotStatus.running:
            logger.info("Engine start skipped: account status is %s", self.account.status)
            return
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
        last_db_check = time()
        async for data in self.stream.stream():
            tick_per_symbol[data.symbol] = tick_per_symbol.get(data.symbol, 0) + 1
            tick_count += 1
            if time() - last_status >= 60:
                logger.info("Ticks received: %d, per symbol: %s", tick_count, tick_per_symbol)
                last_status = time()
            # Check stop signal from API every 5s (DB status is the source of truth)
            if time() - last_db_check >= 5:
                try:
                    self.db.refresh(self.account)
                except Exception:
                    pass
                last_db_check = time()
                if self.account.status != PaperBotStatus.running:
                    logger.info("Tick loop stopping: account status is %s", self.account.status)
                    self.stream.stop()
                    return
            await self.on_tick(data)

    async def _run_entry_loop(self, symbols: list[str]) -> None:
        """Evaluate entries periodically on real candles (independent of ticks)."""
        while self._running:
            settings = get_settings()
            try:
                self.db.refresh(self.account)
            except Exception:
                pass
            # Stop signal from API — exit the loop
            if self.account.status == PaperBotStatus.stopped:
                logger.info("Entry loop stopping: account status is STOPPED")
                return
            if self.account.status == PaperBotStatus.paused:
                self.risk.maybe_auto_resume()
            if self.account.status == PaperBotStatus.running:
                await self._evaluate_entries(symbols, settings)
            await asyncio.sleep(max(int(settings.paper_eval_interval_seconds), 1))

    async def _evaluate_entries(self, symbols: list[str], settings) -> None:
        for symbol in symbols:
            try:
                await self._evaluate_symbol_entry(symbol, settings)
            except Exception as exc:
                # A single symbol's unexpected error must never abort the whole
                # evaluation pass (and crash-restart the worker), leaving every
                # other symbol untraded. Log it and move on.
                logger.warning("paper entry: evaluation failed for %s: %s", symbol, exc)
                self._log(
                    "entry_skipped",
                    f"{symbol}: evaluation_error ({exc})",
                    {"symbol": symbol, "reason": "evaluation_error"},
                )

    async def _evaluate_symbol_entry(self, symbol: str, settings) -> None:
        from app.paper_trading.mirror import resolve_paper_exec

        exec_ = resolve_paper_exec(self.db, settings)
        # Mirror live: trade the live timeframe so signal frequency/quality match.
        paper_interval = exec_.interval
        try:
            candles = await self._client.candles(
                symbol,
                interval=paper_interval,
                limit=settings.candle_history_limit,
                drop_unclosed=True,
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
            return
        if not candles:
            self._log(
                "entry_skipped",
                f"{symbol}: no_candles",
                {"symbol": symbol, "reason": "no_candles"},
            )
            return
        signal = self.strategy.evaluate_real_candles(symbol, candles)
        if signal is None:
            # Message keeps the readable reason (with RSI); payload carries the
            # STABLE code so the diagnostics tally buckets cleanly and stays bounded.
            reason_msg = getattr(self.strategy, "last_reason", "") or "no_signal"
            reason_code = getattr(self.strategy, "last_reason_code", "") or "no_signal"
            self._log("entry_skipped", f"{symbol}: {reason_msg}", {"symbol": symbol, "reason": reason_code})
            return

        # Mirror live: a SPOT live account skips short signals (cannot hold shorts),
        # so paper must too — otherwise paper trades setups that never happen live.
        if not exec_.allow_short and signal.side == PaperSide.sell:
            self._log("entry_skipped", f"{symbol}: short_skipped_spot",
                      {"symbol": symbol, "reason": "short_skipped_spot"})
            return

        # Multi-timeframe confirmation: check HTF trend alignment
        if getattr(settings, "strategy_mtf_enabled", False):
            try:
                htf_candles = await self._client.candles(
                    symbol,
                    interval=settings.strategy_mtf_interval,
                    limit=51,  # +1 so dropping the forming bar still leaves 50
                    drop_unclosed=True,
                )
                if htf_candles and len(htf_candles) >= 50:
                    from app.services.strategy.indicators import ema as calc_ema
                    htf_closes = [Decimal(str(c["close"])) for c in htf_candles]
                    htf_ema = calc_ema(htf_closes, 50)
                    htf_last = htf_closes[-1]
                    direction = signal.metadata.get("direction") if signal.metadata else "long"
                    if direction == "long" and htf_last < htf_ema:
                        self._log("entry_skipped", f"{symbol}: htf_trend_mismatch (long but 4h below EMA50)",
                                  {"symbol": symbol, "reason": "htf_trend_mismatch"})
                        return
                    if direction == "short" and htf_last > htf_ema:
                        self._log("entry_skipped", f"{symbol}: htf_trend_mismatch (short but 4h above EMA50)",
                                  {"symbol": symbol, "reason": "htf_trend_mismatch"})
                        return
            except Exception:
                pass  # MTF check is advisory; proceed if it fails

        # Mirror live: apply the same entry gates the live engine runs in
        # scan_symbol (data-quality, regime, health, correlation) and carry the
        # combined de-risk multiplier into sizing. Only when mirroring, so
        # standalone paper stays lightweight.
        risk_mult = Decimal("1")
        if exec_.mirror:
            allowed, risk_mult = await self._live_entry_gate(symbol, candles, signal, settings)
            if not allowed:
                return

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
        await self.execute_signal(signal, data, risk_mult)

    async def _live_entry_gate(self, symbol, candles, signal, settings) -> tuple[bool, Decimal]:
        """Mirror the live engine's scan_symbol entry filters so paper rejects /
        de-risks entries the same way live would. Returns (allowed, risk_mult).

        Uses the SAME engine classes and call shapes as TradingEngine (not a
        reimplementation). Each filter is best-effort: a failure never blocks the
        entry, matching live's defensive behaviour.
        """
        interval = settings.market_data_interval
        strategy_name = getattr(signal, "strategy", None) or getattr(self.strategy, "name", "")
        risk_mult = Decimal("1")

        # 1. Market-data quality gate (block on INVALID, de-risk on DEGRADED).
        try:
            from app.market_data_quality.engine import MarketDataQualityEngine
            from app.market_data_quality.models import DataTradeStatus

            mdq = MarketDataQualityEngine(self.db).ingest(candles, symbol, interval, source="gateio")
            if mdq.trade_status == DataTradeStatus.invalid and settings.mdq_pause_on_invalid:
                self._log("entry_skipped", f"{symbol}: data_invalid", {"symbol": symbol, "reason": "data_invalid"})
                return False, risk_mult
            if mdq.trade_status == DataTradeStatus.degraded:
                risk_mult *= Decimal(str(settings.mdq_degraded_risk_multiplier))
        except Exception:
            pass

        # 2. Market-regime filter (block / de-risk by regime).
        try:
            from app.market_regime.engine import MarketRegimeEngine

            candles_list = [
                {"open": float(c["open"]), "high": float(c["high"]), "low": float(c["low"]),
                 "close": float(c["close"]), "volume": float(c["volume"]), "timestamp": c["timestamp"]}
                for c in candles
            ]
            regime = MarketRegimeEngine(self.db)
            regime.update_regime(symbol, interval, candles_list)
            allowed, reason, rmult = regime.should_trade(strategy_name, symbol)
            if not allowed:
                self._log("entry_skipped", f"{symbol}: regime_blocked ({reason})",
                          {"symbol": symbol, "reason": "regime_blocked"})
                return False, risk_mult
            risk_mult *= Decimal(str(rmult))
        except Exception:
            pass

        # 3. Strategy-health filter (block when PAUSED/DISABLED, else de-risk).
        try:
            from app.strategy_health.engine import StrategyHealthEngine

            health = StrategyHealthEngine(self.db).update_health(strategy_name) or {}
            if health.get("state") in ("PAUSED", "DISABLED"):
                self._log("entry_skipped", f"{symbol}: health_{health.get('state')}",
                          {"symbol": symbol, "reason": "health_blocked"})
                return False, risk_mult
            risk_mult *= Decimal(str(health.get("risk_multiplier", 1)))
        except Exception:
            pass

        # 4. Funding-rate signal (futures only, de-risk on adverse funding).
        try:
            if settings.trading_market.lower() == "futures" and getattr(settings, "funding_signal_enabled", False):
                funding_data = await self._client.get_futures_funding_rate(symbol) if self._client else None
                if funding_data:
                    rate_raw = funding_data.get("r")
                    if rate_raw not in (None, ""):
                        rate = Decimal(str(rate_raw))
                        threshold = Decimal(str(settings.funding_signal_threshold_pct))
                        is_short = getattr(signal, "side", None) == "sell" or signal.side.value == "sell"
                        adverse = (rate > threshold) if not is_short else (rate < -threshold)
                        if adverse:
                            mult = Decimal(str(settings.funding_signal_risk_mult))
                            if 0 < mult <= 1:
                                risk_mult *= mult
        except Exception:
            pass

        # 5. Order-book imbalance (de-risk when adverse depth wall).
        try:
            if getattr(settings, "orderbook_imbalance_enabled", False) and self._client:
                book = await self._client.get_order_book(symbol, depth=int(settings.orderbook_depth), market=settings.trading_market.lower())
                if book:
                    bids = book.get("bids") or []
                    asks = book.get("asks") or []
                    if bids and asks:
                        bid_depth = sum(float(level[1]) for level in bids if len(level) >= 2)
                        ask_depth = sum(float(level[1]) for level in asks if len(level) >= 2)
                        total = bid_depth + ask_depth
                        if total > 0:
                            imbalance = (bid_depth - ask_depth) / total
                            threshold = float(settings.orderbook_imbalance_threshold)
                            is_short = signal.side.value == "sell"
                            adverse = (imbalance < -threshold) if not is_short else (imbalance > threshold)
                            if adverse:
                                mult = Decimal(str(settings.orderbook_imbalance_risk_mult))
                                if 0 < mult <= 1:
                                    risk_mult *= mult
        except Exception:
            pass

        # 6. Correlation filter (pairwise + aggregate).
        if settings.correlation_filter_enabled:
            try:
                from app.portfolio.correlation import CorrelationEngine, max_correlation

                open_syms = [p.symbol for p in self.portfolio.open_positions() if p.symbol != symbol]
                if open_syms:
                    corr = CorrelationEngine(self.db).calculate_correlation([symbol, *open_syms], interval)
                    mx = max_correlation(corr.get("matrix", {}), symbol, open_syms)
                    if mx > float(settings.max_position_correlation):
                        self._log("entry_skipped", f"{symbol}: correlation {mx:.2f}",
                                  {"symbol": symbol, "reason": "correlation_blocked"})
                        return False, risk_mult
                    # Aggregate correlation cap (mirrors live's max_portfolio_correlation).
                    # Only positive correlations count toward concentration risk;
                    # negative correlations are diversifying and should not block.
                    matrix = corr.get("matrix", {})
                    pair_corrs = []
                    for i, s1 in enumerate([symbol, *open_syms]):
                        for j, s2 in enumerate([symbol, *open_syms]):
                            if i < j:
                                val = matrix.get(s1, {}).get(s2) or matrix.get(s2, {}).get(s1)
                                if val is not None and float(val) > 0:
                                    pair_corrs.append(float(val))
                    if pair_corrs:
                        avg_corr = sum(pair_corrs) / len(pair_corrs)
                        if avg_corr > float(getattr(settings, "max_portfolio_correlation", 0.55)):
                            self._log("entry_skipped", f"{symbol}: avg_correlation {avg_corr:.2f}",
                                      {"symbol": symbol, "reason": "portfolio_correlation_blocked"})
                            return False, risk_mult
            except Exception:
                pass

        return True, risk_mult

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

    async def execute_signal(
        self, signal: TradingSignal, data: MarketData, risk_mult: Decimal = Decimal("1")
    ) -> None:
        approved, reason = self.risk.approve_signal(signal, data)
        if not approved:
            if time() - self._last_risk_log_ts >= 10:
                self._log("risk_check", f"{signal.symbol}: {reason}", {"symbol": signal.symbol, "reason": reason})
                self._last_risk_log_ts = time()
            if reason in {"daily_loss_limit_reached", "max_drawdown_reached"}:
                await self.notifier.send(f"Paper trading paused: {reason}")
            return
        if time() - self._last_risk_log_ts >= 10:
            self._log("risk_check", f"{signal.symbol}: approved", {"symbol": signal.symbol, "reason": "approved"})
            self._last_risk_log_ts = time()
        equity = self.portfolio.equity()
        price = Decimal(str(data.price))
        config = get_settings()
        from app.paper_trading.mirror import resolve_paper_exec

        exec_ = resolve_paper_exec(self.db, config)

        # Fixed-fractional risk sizing. Per-trade risk is risk_pct of equity, sized
        # against the SAME ATR stop the broker will place, so realised risk matches
        # intent. Notional is capped at notional_cap_pct of equity. When mirroring
        # live, all of these come from the live risk config (max_risk_per_trade_pct
        # + StrategySettings), so paper sizes positions exactly as live would.
        risk_pct = exec_.risk_pct
        stop_mult = exec_.atr_stop_multiplier
        notional_cap_qty = (equity * exec_.notional_cap_pct) / price if price > 0 else Decimal("0")
        fallback_qty = (equity * Decimal(str(config.paper_fallback_capital_pct))) / price if price > 0 else Decimal("0")
        fallback_qty = min(fallback_qty, notional_cap_qty)

        atr_str = signal.metadata.get("atr") if signal.metadata else None
        if atr_str and config.risk_based_sizing_enabled:
            try:
                atr_value = Decimal(str(atr_str))
                stop_distance = atr_value * stop_mult
                if stop_distance > 0:
                    risk_based_qty = (equity * risk_pct) / stop_distance
                    quantity = min(risk_based_qty, notional_cap_qty)
                else:
                    quantity = fallback_qty
            except Exception:
                quantity = fallback_qty
        else:
            quantity = fallback_qty

        # Live parity: scale size by the combined de-risk multiplier from the
        # regime/health/data-quality gates (matches the live engine).
        if risk_mult != Decimal("1"):
            quantity = quantity * risk_mult

        if quantity <= 0:
            return

        # Kelly-optimal fraction (opt-in): scale by edge quality once a track record
        # exists. Off by default so cold-start sizing is deterministic.
        if config.paper_kelly_enabled:
            try:
                from app.paper_trading.metrics import PaperMetrics
                metrics = PaperMetrics(self.db, self.account.id).summary()
                wr = metrics.get("win_rate_rolling_100", 0)
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

            # Legacy fixed-pct dynamic stop (opt-in). DISABLED by default: it
            # tightens the stop to a flat % of price, silently overriding the ATR
            # stop the position was sized against and mis-stating realised risk.
            # The ATR stop + breakeven + trailing below govern exits instead.
            if settings.paper_dynamic_pct_stop_enabled and not position.breakeven_triggered and position.stop_loss:
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
            # A take_profit of 0/None means the TP is disabled (trend-following
            # strategies let winners run via trailing + breakeven) — skip the TP
            # check so the position is never exited at price>=0.
            tp_active = position.take_profit is not None and position.take_profit > 0
            if is_short:
                if position.stop_loss and price >= position.stop_loss:
                    reason = "trailing_stop" if position.breakeven_triggered else "stop_loss"
                    self.broker.close_position(position, data, reason)
                    self._log(f"{reason}_triggered", f"{data.symbol} {reason} triggered at ~{price}")
                elif tp_active and position.take_profit and price <= position.take_profit:
                    self.broker.close_position(position, data, "take_profit")
                    self._log("take_profit_triggered", f"{data.symbol} take profit triggered at ~{price}")
            else:
                if position.stop_loss and price <= position.stop_loss:
                    reason = "trailing_stop" if position.breakeven_triggered else "stop_loss"
                    self.broker.close_position(position, data, reason)
                    self._log(f"{reason}_triggered", f"{data.symbol} {reason} triggered at ~{price}")
                elif tp_active and position.take_profit and price >= position.take_profit:
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
        if time() - self._last_log_commit >= 5:
            self.db.commit()
            self._last_log_commit = time()
