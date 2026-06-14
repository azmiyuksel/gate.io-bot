import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.account.engine import AccountManager
from app.core.config import get_settings
from app.execution_quality.engine import ExecutionQualityEngine
from app.market_data_quality.engine import MarketDataQualityEngine
from app.market_data_quality.models import DataTradeStatus
from app.market_regime.engine import MarketRegimeEngine
from app.models.entities import Order, Position, SystemLog, Trade
from app.models.enums import LogLevel, OrderSide, OrderStatus, PositionStatus
from app.repositories.trading import (
    OrderRepository,
    PositionRepository,
    StrategySettingsRepository,
)
from app.services.exchange.gateio import GateIOClient, OrderBelowMinimum
from app.services.notifications.telegram import TelegramNotifier
from app.services.risk.circuit_breaker import CircuitBreaker
from app.services.risk.manager import RiskManager, drawdown_risk_multiplier
from app.services.strategy.signals import CapitalPreservationStrategy
from app.strategy_health.anomaly_detector import StrategyAnomalyDetector
from app.strategy_health.engine import StrategyHealthEngine


def _fee_in_quote(response: dict, price: Decimal, symbol: str) -> Decimal:
    """Normalize an exchange fee to the quote currency.

    On a spot BUY, Gate.io often deducts the fee in the BASE currency (the coin
    received); converting it to quote keeps PnL/equity consistent. Fees already
    in the quote currency pass through unchanged.
    """
    fee = Decimal(str(response.get("fee") or 0))
    fee_ccy = (response.get("fee_currency") or "").upper()
    base_ccy = symbol.split("_")[0].upper()
    if fee_ccy and fee_ccy == base_ccy:
        return fee * price
    return fee


def _fee_in_base(response: dict, symbol: str) -> Decimal:
    """The portion of an exchange fee charged in the BASE currency, if any.

    On a spot BUY the fee is frequently deducted from the coin received, so the
    base quantity actually credited is the fill minus this fee.
    """
    fee_ccy = (response.get("fee_currency") or "").upper()
    base_ccy = symbol.split("_")[0].upper()
    if fee_ccy and fee_ccy == base_ccy:
        return Decimal(str(response.get("fee") or 0))
    return Decimal("0")


def _filled_base_qty(response: dict, fill_price: Decimal, fallback: Decimal) -> Decimal:
    """Base quantity actually filled by an order.

    Gate.io's `filled_total` is denominated in the QUOTE currency (the value
    transacted), NOT the base amount, so deriving base directly from it would be
    wrong. Prefer base = filled_total / avg_deal_price; fall back to
    `amount - left` (valid when `amount` is a base quantity, i.e. sells/limit
    orders), then to the provided fallback.
    """
    filled_total = Decimal(str(response.get("filled_total") or 0))  # quote value filled
    if filled_total > 0 and fill_price > 0:
        return filled_total / fill_price
    amount = Decimal(str(response.get("amount") or 0))
    left = Decimal(str(response.get("left") or 0))
    base = amount - left
    if base > 0:
        return base
    return fallback


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
        self._health_anomaly_detector = StrategyAnomalyDetector()

    async def scan_symbol(self, symbol: str, equity: Decimal) -> None:
        signal_time = datetime.now(UTC)
        # Global kill-switch: no new entries while tripped.
        if self.breaker.is_tripped():
            self._log("circuit_breaker", f"{symbol}: skipped, circuit breaker tripped")
            return

        _settings = get_settings()
        candles = await self.client.candles(
            symbol,
            interval=_settings.market_data_interval,
            limit=_settings.candle_history_limit,
        )

        # Market Data Quality gate: run the feed through the quality pipeline and
        # block trading on unreliable data, de-risk on degraded data.
        mdq_result = MarketDataQualityEngine(self.db).ingest(candles, symbol, get_settings().market_data_interval, source="gateio")
        data_status = mdq_result.trade_status
        if data_status == DataTradeStatus.invalid and get_settings().mdq_pause_on_invalid:
            self._log(
                "data_quality",
                f"{symbol}: trading paused, data INVALID (health={mdq_result.health.score})",
            )
            return
        degraded_mult = Decimal(str(get_settings().mdq_degraded_risk_multiplier))
        data_risk_mult = degraded_mult if data_status == DataTradeStatus.degraded else Decimal("1")

        signal = self.strategy.evaluate(candles)
        if not signal.should_buy or signal.entry_price is None or signal.atr_value is None:
            self._log("strategy", f"{symbol}: {signal.reason}")
            return

        # Market Regime Detection Filter
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
        
        regime_engine.update_regime(symbol, get_settings().market_data_interval, candles_list)
        strategy_name = self.strategy.name
        allowed, reason, risk_mult = regime_engine.should_trade(strategy_name, symbol)
        
        if not allowed:
            self._log("regime_filter", f"{symbol} trade blocked by regime: {reason}")
            return

        # Strategy Health Filter
        health_engine = StrategyHealthEngine(self.db, anomaly_detector=self._health_anomaly_detector)
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
        # Graded de-risking as account drawdown deepens (recovery-math aware).
        dd_mult = Decimal("1")
        _s = get_settings()
        if _s.drawdown_derisk_enabled:
            dd_mult = drawdown_risk_multiplier(
                AccountManager(self.db).drawdown_pct(),
                Decimal(str(_s.max_account_drawdown_pct)),
                Decimal(str(_s.drawdown_derisk_floor)),
            )
        final_quantity = decision.quantity * risk_mult * health_mult * data_risk_mult * dd_mult
        if final_quantity <= 0:
            self._log("risk_filter", f"{symbol} trade quantity scaled to zero by risk filters (regime: {risk_mult}x, health: {health_mult}x, data: {data_risk_mult}x, drawdown: {dd_mult}x)")
            return

        # Pre-trade slippage guard: a market BUY has no price cap, so if the live
        # price has already run away from the signal price, abort rather than chase
        # the fill into adverse slippage.
        entry_slip_band = Decimal(str(_settings.entry_max_slippage_pct))
        if entry_slip_band > 0:
            live_price = await self.client.last_price(symbol)
            if live_price is not None and live_price > 0:
                adverse_move = (live_price - signal.entry_price) / signal.entry_price
                if adverse_move > entry_slip_band:
                    self._log(
                        "slippage_guard",
                        f"{symbol}: entry skipped, price moved {adverse_move:.4%} "
                        f"(live={live_price} signal={signal.entry_price}) > max {entry_slip_band:.2%}",
                    )
                    return

        submission_time = datetime.now(UTC)
        # Market BUY on Gate.io spot takes a QUOTE (USDT) amount to spend.
        quote_amount = final_quantity * signal.entry_price
        try:
            response = await self.client.place_market_buy(symbol, quote_amount)
        except OrderBelowMinimum as exc:
            self._log("order_min", f"{symbol}: buy skipped, {exc}")
            return
        ack_time = datetime.now(UTC)
        # Use the ACTUAL fill price for the entry, not the signal price.
        fill_price = Decimal(str(response.get("avg_deal_price") or signal.entry_price))
        if fill_price <= 0:
            fill_price = signal.entry_price
        # --- Slippage guard: log warning if fill deviates too far from signal price ---
        # Even when slippage exceeds the threshold, the exchange order (IOC) may
        # have been fully or partially filled.  We MUST persist the position and
        # order so that reconciliation, stop-management and PnL tracking can
        # handle it.  Skipping persistence would leave a live exchange position
        # untracked — no stop-loss, no trailing stop, no PnL.
        max_slippage_pct = Decimal(str(get_settings().eq_critical_slippage_pct))
        if signal.entry_price > 0 and max_slippage_pct > 0:
            slippage_pct = abs(fill_price - signal.entry_price) / signal.entry_price
            if slippage_pct > max_slippage_pct:
                self._log(
                    "slippage_guard",
                    f"{symbol}: HIGH SLIPPAGE fill_price={fill_price} signal={signal.entry_price} "
                    f"slippage={slippage_pct:.4%} > max={max_slippage_pct:.2%}. "
                    f"Position will be tracked for reconciliation.",
                    LogLevel.warning,
                )
        # Derive the base quantity actually credited from the real fill (not the
        # pre-order estimate) and subtract any fee charged in the base currency —
        # Gate.io deducts the spot BUY fee from the coin received, so the tracked
        # size must match what we can later sell.
        gross_base_qty = _filled_base_qty(response, fill_price, final_quantity)
        actual_base_qty = gross_base_qty - _fee_in_base(response, symbol)
        if actual_base_qty <= 0:
            actual_base_qty = gross_base_qty
        position = Position(
            symbol=symbol,
            entry_price=fill_price,
            quantity=actual_base_qty,
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
            price=fill_price,
            quantity=actual_base_qty,
            raw_response=json.dumps(response),
        )
        self.db.add(order)
        # The exchange order is already live; on persist failure roll back so the
        # session is consistent and let reconciliation recover the order state.
        self._commit_or_rollback(
            f"{symbol}: failed to persist order {response.get('id')}, rolled back"
        )
        self.db.refresh(order)

        self._record_execution_quality(
            strategy_name=strategy_name,
            symbol=symbol,
            side="buy",
            expected_price=signal.entry_price,
            expected_quantity=actual_base_qty,
            signal_time=signal_time,
            submission_time=submission_time,
            order_id=order.id,
            fill_price=fill_price,
            fill_quantity=gross_base_qty,
            fee=_fee_in_quote(response, fill_price, symbol),
            ack_time=ack_time,
        )

        await self.notifier.send(f"Opened {symbol}: qty={actual_base_qty} entry={fill_price}")


    async def manage_open_positions(self) -> None:
        for position in self.positions.open_positions():
            try:
                candles = await self.client.candles(position.symbol, limit=2)
                if not candles:
                    self._log(
                        "empty_candle",
                        f"{position.symbol}: no candle data, skipping stop management",
                        LogLevel.warning,
                    )
                    continue
                latest = candles[-1]
                # Use the authoritative live ticker price; fall back to the latest
                # candle close only if the ticker is unavailable.
                price = await self.client.last_price(position.symbol)
                if price is None or price <= 0:
                    price = Decimal(str(latest["close"]))

                stop_hit = price <= position.stop_loss
                tp_hit = price >= position.take_profit
                # Intrabar gap protection: between 15-minute polls the price can wick
                # through a level and recover. Catch that via the candle's low/high —
                # but only for candles that fully postdate entry, so a pre-entry wick
                # cannot false-trigger a freshly opened position.
                opened = position.opened_at
                if opened is not None and opened.tzinfo is None:
                    opened = opened.replace(tzinfo=UTC)
                candle_start = datetime.fromtimestamp(int(latest["timestamp"]), tz=UTC)
                if opened is None or candle_start >= opened:
                    if Decimal(str(latest["low"])) <= position.stop_loss:
                        stop_hit = True
                    if Decimal(str(latest["high"])) >= position.take_profit:
                        tp_hit = True

                # Evaluate the stop before the take-profit — protect capital first.
                if stop_hit:
                    await self.close_position(position, "stop_loss")
                elif tp_hit:
                    await self.close_position(position, "take_profit")
                else:
                    self._update_trailing_stop(position, price)
            except Exception as exc:
                self._log(
                    "position_manage_error",
                    f"{position.symbol}: {exc}",
                    LogLevel.error,
                )

    async def close_position(self, position: Position, reason: str, _retry: int = 3) -> Order:
        last_exc: Exception | None = None
        for attempt in range(_retry):
            try:
                return await self._close_position_inner(position, reason, attempt)
            except Exception as exc:
                last_exc = exc
                if attempt < _retry - 1:
                    self._log(
                        "close_retry",
                        f"{position.symbol}: attempt {attempt + 1} failed ({exc}), retrying",
                        LogLevel.warning,
                    )
                    await self.notifier.send(
                        f"⚠️ {position.symbol} close attempt {attempt + 1} failed: {exc}"
                    )
                    import asyncio
                    await asyncio.sleep(1)
        # All retries exhausted — position is still open; alert and let reconciliation recover.
        self._log(
            "close_failed",
            f"{position.symbol}: FAILED to close after {_retry} attempts ({reason}): {last_exc}",
            LogLevel.error,
        )
        await self.notifier.send(
            f"🔴 CRITICAL: {position.symbol} FAILED to close ({reason}) after {_retry} attempts! "
            f"Manual intervention may be required. Last error: {last_exc}"
        )
        raise last_exc  # type: ignore[misc]

    async def _close_position_inner(
        self, position: Position, reason: str, attempt: int
    ) -> Order:
        signal_time = datetime.now(UTC)
        submission_time = datetime.now(UTC)
        response = await self.client.place_market_sell(position.symbol, position.quantity)
        ack_time = datetime.now(UTC)

        exit_price = Decimal(str(response.get("avg_deal_price") or position.entry_price))
        # `filled_total` is QUOTE-denominated; derive the base quantity sold.
        filled_qty = _filled_base_qty(response, exit_price, position.quantity)
        fee = _fee_in_quote(response, exit_price, position.symbol)
        pnl = (exit_price - position.entry_price) * filled_qty - fee

        if filled_qty < position.quantity:
            position.quantity = position.quantity - filled_qty
            position.status = PositionStatus.open
        else:
            position.status = PositionStatus.closed
            position.closed_at = datetime.now(UTC)
        # Accumulate realized PnL across partial closes instead of overwriting it.
        position.realized_pnl = (position.realized_pnl or Decimal("0")) + pnl

        order = Order(
            exchange_order_id=str(response.get("id")),
            position_id=position.id,
            symbol=position.symbol,
            side=OrderSide.sell,
            status=OrderStatus.open,
            price=exit_price,
            quantity=filled_qty,
            raw_response=json.dumps(response),
        )
        self.db.add(order)
        self.db.flush()
        trade = Trade(
            order_id=order.id,
            strategy_name=self.strategy.name,
            symbol=position.symbol,
            side=OrderSide.sell,
            price=exit_price,
            quantity=filled_qty,
            fee=fee,
            realized_pnl=pnl,
        )
        self.db.add(trade)
        self._commit_or_rollback(
            f"{position.symbol}: failed to persist close {response.get('id')}, rolled back"
        )
        self.db.refresh(order)

        self._record_execution_quality(
            strategy_name=self.strategy.name,
            symbol=position.symbol,
            side="sell",
            expected_price=exit_price,
            expected_quantity=position.quantity,
            signal_time=signal_time,
            submission_time=submission_time,
            order_id=order.id,
            fill_price=exit_price,
            fill_quantity=filled_qty,
            fee=fee,
            ack_time=ack_time,
        )

        await self.notifier.send(f"Closed {position.symbol}: {reason}, pnl={pnl}")
        return order

    def _trailing_stop_pct(self) -> Decimal:
        """Configured trailing-stop distance from StrategySettings, falling back
        to the app-level default (default 1%)."""
        settings = StrategySettingsRepository(self.db).current()
        pct = settings.trailing_stop_pct if settings is not None else None
        if pct is None:
            pct = Decimal(str(get_settings().strategy_trailing_stop_pct))
        # Clamp to a sane (0, 1) range so a misconfiguration cannot widen the stop.
        if pct <= 0 or pct >= 1:
            pct = Decimal(str(get_settings().strategy_trailing_stop_pct))
        return Decimal(str(pct))

    def _update_trailing_stop(self, position: Position, price: Decimal) -> None:
        if position.trailing_stop and price <= position.trailing_stop:
            return
        new_stop = price * (Decimal("1") - self._trailing_stop_pct())
        if new_stop > position.stop_loss:
            position.stop_loss = new_stop
            position.trailing_stop = new_stop
            self.db.commit()
        # Breakeven stop: once unrealized profit exceeds the trigger threshold,
        # move stop-loss to entry price so the trade cannot become a loss.
        if not position.breakeven_stop:
            trigger_pct = Decimal(str(get_settings().breakeven_stop_trigger_pct))
            if trigger_pct > 0:
                profit_pct = (price - position.entry_price) / position.entry_price
                if profit_pct >= trigger_pct and position.stop_loss < position.entry_price:
                    position.stop_loss = position.entry_price
                    position.breakeven_stop = True
                    self._log(
                        "breakeven_stop",
                        f"{position.symbol}: stop moved to breakeven ({position.entry_price})",
                    )
                    self.db.commit()

    def _commit_or_rollback(self, error_detail: str) -> None:
        """Commit; on failure roll back, log, and re-raise (exchange order is live,
        reconciliation will recover it). Shared by entry and exit persistence."""
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            self._log("trade_persist_error", error_detail, LogLevel.error)
            raise

    def _record_execution_quality(
        self,
        *,
        strategy_name: str,
        symbol: str,
        side: str,
        expected_price: Decimal,
        expected_quantity: Decimal,
        signal_time: datetime,
        submission_time: datetime,
        order_id: int,
        fill_price: Decimal,
        fill_quantity: Decimal,
        fee: Decimal,
        ack_time: datetime,
    ) -> None:
        """Best-effort TCA recording shared by entry and exit. A failure here must
        never abort the trade, so it uses a savepoint (nested transaction) and only
        rolls back its own writes without affecting the already-committed trade."""
        savepoint = self.db.begin_nested()
        try:
            eq_engine = ExecutionQualityEngine(self.db)
            exec_order = eq_engine.record_order(
                strategy_name=strategy_name,
                symbol=symbol,
                side=side,
                expected_price=expected_price,
                expected_quantity=expected_quantity,
                signal_time=signal_time,
                submission_time=submission_time,
                order_id=order_id,
            )
            eq_engine.record_fill(
                execution_order_id=exec_order.id,
                fill_price=fill_price,
                fill_quantity=fill_quantity,
                fee=fee,
                fill_time=datetime.now(UTC),
                ack_time=ack_time,
            )
            savepoint.commit()
        except Exception as e:
            savepoint.rollback()
            self._log("execution_quality_error", f"Failed to record execution quality ({side} {symbol}): {e}")

    def _log(self, source: str, message: str, level: LogLevel = LogLevel.info) -> None:
        self.db.add(SystemLog(level=level, source=source, message=message))
        self.db.commit()

