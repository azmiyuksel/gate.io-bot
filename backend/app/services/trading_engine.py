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
from app.portfolio.correlation import CorrelationEngine, max_correlation
from app.repositories.trading import (
    OrderRepository,
    PositionRepository,
    StrategySettingsRepository,
)
from app.services.exchange.gateio import GateIOClient, OrderBelowMinimum
from app.services.notifications.telegram import TelegramNotifier
from app.services.risk.circuit_breaker import CircuitBreaker
from app.services.risk.manager import RiskManager, drawdown_risk_multiplier
from app.services.strategy.factory import build_strategy
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
        # Mirror paper: the live strategy is selected from config (default momentum).
        self.strategy = build_strategy(get_settings().live_strategy)
        self.risk = RiskManager(db)
        self.breaker = CircuitBreaker(db)
        self.positions = PositionRepository(db)
        self.orders = OrderRepository(db)
        self.notifier = TelegramNotifier()
        self._health_anomaly_detector = StrategyAnomalyDetector()

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def scan_symbol(self, symbol: str, equity: Decimal) -> None:
        if not self._check_circuit_breaker(symbol):
            return

        # Per-symbol guard: never stack a second position on a pair we already
        # hold (mirrors paper's `already_in_position`). Without this a sustained
        # breakout re-fires every cycle and concentrates several entries on one
        # symbol/direction — defeating max_open_positions / exposure diversification.
        if self.positions.has_open(symbol):
            self._log("already_in_position", f"{symbol}: skipped, position already open")
            self.db.commit()
            return

        result = await self._fetch_and_validate_candles(symbol)
        if result is None:
            return
        candles, data_risk_mult = result

        signal = self._evaluate_strategy_signal(symbol, candles)
        if signal is None:
            return

        # Higher-timeframe trend confirmation (mirrors paper). Live previously
        # ignored strategy_mtf_enabled entirely, so live took entries paper would
        # reject — another paper/live divergence now closed.
        if not await self._check_mtf_filter(symbol, signal):
            return

        # Convert exchange candles to list of dicts for feature calculation
        candles_list = [
            {
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c["volume"]),
                "timestamp": c["timestamp"],
            }
            for c in candles
        ]

        allowed, _reason, risk_mult = self._check_regime_filter(symbol, candles_list)
        if not allowed:
            return

        strategy_name = self.strategy.name

        health_status = self._check_strategy_health(strategy_name)
        health_state = health_status.get("state")
        if health_state in ("PAUSED", "DISABLED"):
            self._log("health_filter", f"{symbol} trade blocked: strategy health is {health_state}")
            self.db.commit()
            return

        health_mult = Decimal(str(health_status.get("risk_multiplier", 1)))

        result = self._approve_risk_and_size(symbol, equity, signal, risk_mult, health_mult, data_risk_mult)
        if result is None:
            return
        final_quantity, stop_loss, take_profit = result

        if not self._check_correlation_filter(symbol):
            return

        if not await self._check_slippage_guard(symbol, signal):
            return

        await self._execute_entry(
            symbol, signal, final_quantity, stop_loss, take_profit, strategy_name, equity
        )

    # ------------------------------------------------------------------
    # Private helpers — extracted from scan_symbol
    # ------------------------------------------------------------------

    def _check_circuit_breaker(self, symbol: str) -> bool:
        """Global kill-switch: no new entries while tripped."""
        if self.breaker.is_tripped():
            self._log("circuit_breaker", f"{symbol}: skipped, circuit breaker tripped")
            self.db.commit()
            return False
        return True

    async def _fetch_and_validate_candles(self, symbol: str):
        """Fetch candles and run through the market-data quality pipeline.

        Returns (candles, data_risk_mult) on success, None when data is invalid
        and mdq_pause_on_invalid is enabled.
        """
        _settings = get_settings()
        candles = await self.client.candles(
            symbol,
            interval=_settings.market_data_interval,
            limit=_settings.candle_history_limit,
            drop_unclosed=True,
        )

        # Market Data Quality gate: run the feed through the quality pipeline and
        # block trading on unreliable data, de-risk on degraded data.
        mdq_result = MarketDataQualityEngine(self.db).ingest(
            candles, symbol, get_settings().market_data_interval, source="gateio"
        )
        data_status = mdq_result.trade_status
        if data_status == DataTradeStatus.invalid and get_settings().mdq_pause_on_invalid:
            self._log(
                "data_quality",
                f"{symbol}: trading paused, data INVALID (health={mdq_result.health.score})",
            )
            self.db.commit()
            return None
        degraded_mult = Decimal(str(get_settings().mdq_degraded_risk_multiplier))
        data_risk_mult = degraded_mult if data_status == DataTradeStatus.degraded else Decimal("1")
        return candles, data_risk_mult

    def _evaluate_strategy_signal(self, symbol: str, candles: list):
        """Run the strategy against the candle feed.

        Returns the signal object when a valid buy signal is present; returns None
        (after logging and committing) otherwise.
        """
        signal = self.strategy.evaluate(candles)
        if not signal.should_enter or signal.entry_price is None or signal.atr_value is None:
            self._log("strategy", f"{symbol}: {signal.reason}")
            self.db.commit()
            return None
        return signal

    def _check_regime_filter(self, symbol: str, candles_list: list):
        """Update market regime and check whether the strategy is allowed to trade.

        Returns (allowed: bool, reason: str, risk_mult: Decimal).  Logs and
        commits when trading is blocked by the regime filter.
        """
        regime_engine = MarketRegimeEngine(self.db)
        regime_engine.update_regime(symbol, get_settings().market_data_interval, candles_list)
        strategy_name = self.strategy.name
        allowed, reason, risk_mult = regime_engine.should_trade(strategy_name, symbol)
        if not allowed:
            self._log("regime_filter", f"{symbol} trade blocked by regime: {reason}")
            self.db.commit()
        return allowed, reason, risk_mult

    def _check_strategy_health(self, strategy_name: str) -> dict:
        """Run the strategy-health engine and return the health-status dict."""
        health_engine = StrategyHealthEngine(self.db, anomaly_detector=self._health_anomaly_detector)
        health_status = health_engine.update_health(strategy_name) or {}
        return health_status

    def _approve_risk_and_size(
        self, symbol: str, equity: Decimal, signal, risk_mult: Decimal,
        health_mult: Decimal, data_risk_mult: Decimal,
    ):
        """Run the risk manager and scale the position quantity by all active
        risk multipliers (regime, health, data-quality, drawdown).

        Returns (final_quantity, stop_loss, take_profit) on success, None when
        the risk manager rejects the entry or the scaled quantity is <= 0.
        """
        decision = self.risk.approve_entry(
            equity,
            signal.entry_price,
            signal.atr_value,
            side=getattr(signal, "direction", "long"),
            expectancy_type=getattr(signal, "expectancy_type", "reversion"),
        )
        if not decision.allowed:
            self._log("risk", f"{symbol}: {decision.reason}")
            self.db.commit()
            return None

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
            self._log(
                "risk_filter",
                f"{symbol} trade quantity scaled to zero by risk filters "
                f"(regime: {risk_mult}x, health: {health_mult}x, data: {data_risk_mult}x, drawdown: {dd_mult}x)",
            )
            self.db.commit()
            return None
        return final_quantity, decision.stop_loss, decision.take_profit

    def _check_correlation_filter(self, symbol: str) -> bool:
        """Correlation-aware portfolio guard: block a new entry that is too
        correlated with already-open positions, so several "diversified" trades
        don't become one concentrated directional bet.

        Two checks:
          1. Pairwise: the candidate's max correlation with ANY open position
             must stay below `max_position_correlation`.
          2. Aggregate: the MEAN pairwise correlation across the candidate +
             all open positions must stay below `max_portfolio_correlation`.
             The pairwise cap alone lets 8 positions at 0.64 corr each pass —
             effectively one 8x directional bet. The aggregate cap catches
             that concentration.
        """
        if not get_settings().correlation_filter_enabled:
            return True
        open_syms = [p.symbol for p in self.positions.open_positions() if p.symbol != symbol]
        if not open_syms:
            return True
        corr = CorrelationEngine(self.db).calculate_correlation(
            [symbol, *open_syms], get_settings().market_data_interval
        )
        matrix = corr.get("matrix", {})
        # 1. Pairwise cap.
        mx = max_correlation(matrix, symbol, open_syms)
        if mx > float(get_settings().max_position_correlation):
            self._log(
                "correlation_filter",
                f"{symbol}: skipped, pairwise correlation {mx:.2f} with an open position "
                f"> {get_settings().max_position_correlation}",
            )
            self.db.commit()
            return False
        # 2. Aggregate portfolio correlation cap.
        agg_cap = float(getattr(get_settings(), "max_portfolio_correlation", 0) or 0)
        if agg_cap > 0 and len(open_syms) >= 2:
            all_syms = [symbol, *open_syms]
            pair_corrs = []
            for i in range(len(all_syms)):
                for j in range(i + 1, len(all_syms)):
                    row = matrix.get(all_syms[i], {})
                    val = row.get(all_syms[j])
                    if val is not None:
                        pair_corrs.append(float(val))
            if pair_corrs:
                agg = sum(pair_corrs) / len(pair_corrs)
                if agg > agg_cap:
                    self._log(
                        "correlation_filter",
                        f"{symbol}: skipped, aggregate portfolio correlation {agg:.2f} "
                        f"> {agg_cap:.2f} ({len(open_syms)} open positions too concentrated)",
                    )
                    self.db.commit()
                    return False
        return True

    async def _check_mtf_filter(self, symbol: str, signal) -> bool:
        """Multi-timeframe confirmation: require the higher-timeframe (e.g. 4h)
        trend to agree with the entry direction. Advisory — a fetch/indicator
        failure does not block the entry. Mirrors the paper engine so live and
        paper apply the same gate."""
        _settings = get_settings()
        if not getattr(_settings, "strategy_mtf_enabled", False):
            return True
        direction = getattr(signal, "direction", "long") or "long"
        try:
            # +1 so dropping the still-forming bar still leaves 50 closed bars.
            htf = await self.client.candles(
                symbol, interval=_settings.strategy_mtf_interval, limit=51, drop_unclosed=True
            )
        except Exception:
            return True
        if not htf or len(htf) < 50:
            return True
        from app.services.strategy.indicators import ema as calc_ema

        closes = [Decimal(str(c["close"])) for c in htf]
        htf_ema = calc_ema(closes, 50)
        if htf_ema is None or htf_ema <= 0:
            return True
        last = closes[-1]
        if direction == "long" and last < htf_ema:
            self._log(
                "mtf_filter",
                f"{symbol}: long skipped, {_settings.strategy_mtf_interval} trend below EMA50 (HTF downtrend)",
            )
            self.db.commit()
            return False
        if direction == "short" and last > htf_ema:
            self._log(
                "mtf_filter",
                f"{symbol}: short skipped, {_settings.strategy_mtf_interval} trend above EMA50 (HTF uptrend)",
            )
            self.db.commit()
            return False
        return True

    async def _check_slippage_guard(self, symbol: str, signal) -> bool:
        """Pre-trade slippage guard: a market order has no price cap, so if the
        live price has already moved adversely beyond the signal price, abort
        rather than chase the fill. Direction-aware: a LONG is hurt when price
        rises (pay more); a SHORT is hurt when price falls (sell less)."""
        _settings = get_settings()
        entry_slip_band = Decimal(str(_settings.entry_max_slippage_pct))
        if entry_slip_band <= 0:
            return True
        live_price = await self.client.last_price(symbol)
        if live_price is None or live_price <= 0:
            return True
        is_short = (getattr(signal, "direction", "long") or "long") == "short"
        # Long adverse: price rose (buy costs more). Short adverse: price fell
        # (sell proceeds less). Both expressed as a positive adverse fraction.
        if is_short:
            adverse_move = (signal.entry_price - live_price) / signal.entry_price
        else:
            adverse_move = (live_price - signal.entry_price) / signal.entry_price
        if adverse_move > entry_slip_band:
            direction = "short" if is_short else "long"
            self._log(
                "slippage_guard",
                f"{symbol}: {direction} entry skipped, price moved {adverse_move:.4%} "
                f"(live={live_price} signal={signal.entry_price}) > max {entry_slip_band:.2%}",
            )
            self.db.commit()
            return False
        return True

    # ------------------------------------------------------------------
    # Order submission (adaptive limit / market / split)
    # ------------------------------------------------------------------

    def _entry_order_mode(self, signal) -> str:
        """Decide the order type for this entry: 'market', 'limit', or 'adaptive'.

        Honors `entry_order_type` config, with a TCA feedback loop: when recent
        fill slippage exceeds `tca_slippage_feedback_pct`, the next entry is
        forced to a passive limit order to capture the maker rebate instead of
        paying taker slippage repeatedly.
        """
        _settings = get_settings()
        mode = (_settings.entry_order_type or "market").lower()
        if mode not in ("market", "limit", "adaptive"):
            mode = "market"
        # TCA feedback: high recent slippage -> force a maker limit next time.
        feedback_pct = float(getattr(_settings, "tca_slippage_feedback_pct", 0) or 0)
        if feedback_pct > 0 and mode == "market":
            try:
                from app.execution_quality.engine import ExecutionQualityEngine

                recent_slippage = ExecutionQualityEngine(self.db).recent_slippage_pct(signal.direction or "long")
                if recent_slippage is not None and recent_slippage > feedback_pct:
                    self._log(
                        "tca_feedback",
                        f"Forcing limit entry: recent slippage {recent_slippage:.4%} > "
                        f"feedback threshold {feedback_pct:.2%}",
                    )
                    return "limit"
            except Exception:
                pass
        return mode

    async def _submit_entry_order(
        self, symbol: str, signal, final_quantity: Decimal, equity: Decimal
    ) -> dict:
        """Submit the entry order according to the configured mode.

        - market: single market IOC (current behavior, pays taker + slippage).
        - limit: passive maker limit at the signal price (may miss; no slippage).
        - adaptive: try a passive limit first with a short timeout; on timeout
          cancel and fall back to a market order (captures the maker rebate when
          possible without sacrificing fill rate).

        Large notionals (above entry_split_threshold_pct of equity) are split
        into N TWAP child orders to reduce market impact on less-liquid altcoins.
        Returns the aggregate response dict (id of the first/primary child,
        avg_deal_price = volume-weighted average across children).
        """
        _settings = get_settings()
        market = _settings.trading_market.lower()
        mode = self._entry_order_mode(signal)
        notional = float(final_quantity * signal.entry_price)
        from app.execution_quality.splitter import plan_split

        split = plan_split(
            final_quantity, notional, float(equity),
            threshold_pct=float(_settings.entry_split_threshold_pct),
            child_count=int(_settings.entry_split_child_count),
        )

        async def submit_one(qty: Decimal) -> dict:
            if market == "futures":
                if mode == "market":
                    return await self.client.place_futures_market_order(symbol, qty, signal.direction)
                # limit / adaptive: place a maker limit at the signal price.
                return await self.client.place_futures_limit_order(
                    symbol, qty, signal.direction, signal.entry_price
                )
            else:
                if mode == "market":
                    return await self.client.place_market_buy(symbol, qty * signal.entry_price)
                return await self.client.place_limit_buy(symbol, qty * signal.entry_price, signal.entry_price)

        # No split: single order (with adaptive limit->market fallback for one).
        if split is None or not split.should_split:
            if mode == "adaptive":
                return await self._adaptive_limit_entry(symbol, signal, final_quantity, submit_one)
            return await submit_one(final_quantity)
        # Split: submit children ~delay apart. For adaptive mode each child is
        # itself adaptive (limit-then-market); for market/limit all children use
        # the same mode. Aggregate the responses.
        self._log(
            "order_split",
            f"{symbol}: splitting entry notional {notional:.2f} into {len(split.child_quantities)} "
            f"TWAP children ({mode} mode)",
        )
        from app.execution_quality.splitter import execute_split

        async def submit_child(qty: Decimal) -> dict:
            if mode == "adaptive":
                return await self._adaptive_limit_entry(symbol, signal, qty, submit_one)
            return await submit_one(qty)

        responses = await execute_split(submit_child, split)
        return self._aggregate_split_responses(responses, signal)

    async def _adaptive_limit_entry(self, symbol: str, signal, quantity: Decimal, submit_market) -> dict:
        """Try a passive maker limit; on timeout fall back to a market order.

        Posts a limit at the signal price, polls its status for
        `entry_limit_timeout_seconds`, and if it has not filled by then cancels
        it and submits a market order. Returns the (possibly partial) limit fill
        if it filled, or the market fill response on fallback.
        """
        _settings = get_settings()
        timeout = int(_settings.entry_limit_timeout_seconds)
        market = _settings.trading_market.lower()
        try:
            if market == "futures":
                limit_resp = await self.client.place_futures_limit_order(
                    symbol, quantity, signal.direction, signal.entry_price
                )
            else:
                limit_resp = await self.client.place_limit_buy(
                    symbol, quantity * signal.entry_price, signal.entry_price
                )
        except OrderBelowMinimum:
            # A limit below min falls back to market (which may also be below min,
            # in which case the market path raises and the caller skips).
            return await submit_market(quantity)
        order_id = str(limit_resp.get("id") or "")
        if not order_id:
            return await submit_market(quantity)
        # Poll for fill. Poll every ~3s up to the timeout.
        import asyncio

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(3)
            try:
                if market == "futures":
                    status = await self.client.get_futures_order_status(symbol, order_id)
                else:
                    status = await self.client.get_order_status(symbol, order_id)
            except Exception:
                break
            state = str(status.get("status") or status.get("state") or "").lower()
            # Gate.io spot: "closed"/"filled". Futures: "finished".
            if state in ("closed", "filled", "finished") or (
                status.get("left") is not None and Decimal(str(status.get("left"))) == 0
            ):
                # Fully filled as a maker — return the limit fill (no slippage).
                return status
        # Timeout: cancel the limit and fall back to a market order for the
        # unfilled remainder. Any partial fill on the limit is kept; the market
        # order tops up the rest. For simplicity here we cancel and resubmit the
        # full quantity as market (reconciliation will net the partial against
        # the new market fill). A refined version would compute the unfilled
        # remainder and only top that up.
        try:
            if market == "futures":
                await self.client.cancel_futures_order(symbol, order_id)
            else:
                await self.client.cancel_spot_order(symbol, order_id)
        except Exception:
            pass
        self._log(
            "adaptive_limit_timeout",
            f"{symbol}: maker limit timed out after {timeout}s, falling back to market",
            LogLevel.warning,
        )
        return await submit_market(quantity)

    @staticmethod
    def _aggregate_split_responses(responses: list, signal) -> dict:
        """Aggregate per-child responses into a single pseudo-response so the
        existing persist/TCA path works unchanged. Uses the first child's id and
        a volume-weighted average fill price across filled children."""
        filled = [r for r in responses if r and (r.get("avg_deal_price") or r.get("fill_price"))]
        if not filled:
            # All children failed — return the first response (or a stub) so the
            # caller's fill_price fallback to signal.entry kicks in and no
            # position is persisted with a bogus price.
            return responses[0] if responses else {"id": None}
        total_quote = Decimal("0")
        total_base = Decimal("0")
        for r in filled:
            price = Decimal(str(r.get("avg_deal_price") or r.get("fill_price") or 0))
            if price <= 0:
                continue
            filled_total = Decimal(str(r.get("filled_total") or 0))
            total_quote += filled_total
            total_base += filled_total / price if price > 0 else Decimal("0")
        vwap = total_quote / total_base if total_base > 0 else signal.entry_price
        return {
            "id": str(filled[0].get("id") or ""),
            "avg_deal_price": str(vwap),
            "filled_total": str(total_quote),
            "fee": str(sum(Decimal(str(r.get("fee") or 0)) for r in filled)),
            "fee_currency": filled[0].get("fee_currency"),
        }

    async def _execute_entry(
        self, symbol: str, signal, final_quantity: Decimal,
        stop_loss: Decimal, take_profit: Decimal, strategy_name: str,
        equity: Decimal = Decimal("0"),
    ) -> None:
        """Place a market buy, persist Position + Order, record execution quality,
        and notify.  Handles OrderBelowMinimum gracefully."""
        signal_time = datetime.now(UTC)
        submission_time = datetime.now(UTC)
        direction = getattr(signal, "direction", "long") or "long"
        market = get_settings().trading_market.lower()
        is_short = direction == "short"
        side_enum = OrderSide.sell if is_short else OrderSide.buy

        # Spot cannot hold shorts: skip the signal rather than silently BUYING it
        # (the previous behaviour). Enable futures to trade shorts.
        if is_short and market != "futures":
            self._log(
                "short_skipped",
                f"{symbol}: short signal skipped (spot market; set TRADING_MARKET=futures to trade shorts)",
            )
            self.db.commit()
            return

        try:
            if market == "futures":
                # Set leverage and VERIFY it took effect — a silent failure here
                # could place the order at the account's pre-existing (possibly
                # much higher) leverage, blowing past the 2% risk budget. The
                # old `except Exception: pass` swallowed this. Now it is fatal
                # to the entry (the position is never opened at the wrong
                # leverage); the local poll / existing stops keep guarding any
                # already-open positions.
                try:
                    await self.client.set_futures_leverage(symbol, get_settings().futures_leverage)
                except Exception as exc:
                    self._log(
                        "leverage_set_failed",
                        f"{symbol}: FAILED to set leverage {get_settings().futures_leverage}x: {exc}. "
                        f"Entry aborted — refusing to trade at an unverified leverage.",
                        LogLevel.error,
                    )
                    await self.notifier.send(
                        f"\u26a0\ufe0f {symbol}: leverage set FAILED ({exc}). Entry aborted."
                    )
                    self.db.commit()
                    return
                # Read back the contract leverage and abort on mismatch. Gate.io
                # applies leverage per-contract; the position row carries it once
                # a position exists. We verify via the position endpoint right
                # after the set call (an existing position reflects the setting;
                # a flat contract returns no position, in which case we trust the
                # set call's success).
                if get_settings().futures_leverage_verify:
                    try:
                        fut_pos = await self.client.get_futures_position(symbol)
                        if fut_pos:
                            actual_lev = int(fut_pos.get("leverage") or 0)
                            if actual_lev and actual_lev != int(get_settings().futures_leverage):
                                self._log(
                                    "leverage_mismatch",
                                    f"{symbol}: configured leverage {get_settings().futures_leverage}x "
                                    f"but contract reports {actual_lev}x. Entry aborted.",
                                    LogLevel.error,
                                )
                                await self.notifier.send(
                                    f"\u26a0\ufe0f {symbol}: LEVERAGE MISMATCH — configured "
                                    f"{get_settings().futures_leverage}x, exchange reports {actual_lev}x. Entry aborted."
                                )
                                self.db.commit()
                                return
                    except Exception as exc:
                        # Read-back failure is non-fatal (the set call succeeded);
                        # log and proceed, since aborting on a transient read
                        # failure would block all entries under flaky networks.
                        self._log(
                            "leverage_verify_failed",
                            f"{symbol}: leverage read-back failed ({exc}); proceeding (set call succeeded)",
                            LogLevel.warning,
                        )
            # Submit via the adaptive/limit/market + split path.
            response = await self._submit_entry_order(symbol, signal, final_quantity, equity)
        except OrderBelowMinimum as exc:
            self._log("order_min", f"{symbol}: {direction} entry skipped, {exc}")
            return
        ack_time = datetime.now(UTC)

        # Use the ACTUAL fill price for the entry, not the signal price.
        fill_price = Decimal(str(response.get("avg_deal_price") or response.get("fill_price") or signal.entry_price))
        if fill_price <= 0:
            fill_price = signal.entry_price
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
        if market == "futures":
            # Futures size is tracked in the base units we requested (contracts are
            # rounded down to ~final_quantity); fees are quote-denominated, so there
            # is no base-currency deduction as on a spot buy.
            gross_base_qty = final_quantity
            actual_base_qty = final_quantity
        else:
            gross_base_qty = _filled_base_qty(response, fill_price, final_quantity)
            actual_base_qty = gross_base_qty - _fee_in_base(response, symbol)
            if actual_base_qty <= 0:
                actual_base_qty = gross_base_qty

        position = Position(
            symbol=symbol,
            side=side_enum,
            entry_price=fill_price,
            quantity=actual_base_qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self.db.add(position)
        self.db.flush()

        order = Order(
            exchange_order_id=str(response.get("id")),
            position_id=position.id,
            symbol=symbol,
            side=side_enum,
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
            side=side_enum.value,
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

        # Place the protective stop on the EXCHANGE so it rests there and
        # protects the position even if the scheduler is stuck/crashed or a
        # fast adverse move gaps through the 15-min local poll. Best-effort:
        # on failure the local poll remains as a degraded safety net (logged).
        await self._place_exchange_stop(position)

        await self.notifier.send(f"Opened {direction.upper()} {symbol}: qty={actual_base_qty} entry={fill_price}")

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

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

                # Liquidation guard (futures only): read back the exchange's
                # liquidation price and force-close before the liquidation engine
                # fires. With 5x leverage a fast adverse move can hit liquidation
                # faster than the 15-min-polled ATR stop — this closes first.
                if await self._check_liquidation_risk(position, price):
                    continue

                # Direction-aware exits: a SHORT's protective stop sits ABOVE entry
                # (rising price is the loss) and its target BELOW entry, mirrored.
                # A take_profit of 0 means the TP is disabled (trend-following
                # strategies let winners run via trailing + breakeven) — skip the
                # TP check so the position is never exited at price>=0.
                is_short = position.side == OrderSide.sell
                tp_active = position.take_profit is not None and position.take_profit > 0
                if is_short:
                    stop_hit = price >= position.stop_loss
                    tp_hit = tp_active and price <= position.take_profit
                else:
                    stop_hit = price <= position.stop_loss
                    tp_hit = tp_active and price >= position.take_profit
                # Intrabar gap protection: between 15-minute polls the price can wick
                # through a level and recover. Catch that via the candle's low/high —
                # but only for candles that fully postdate entry, so a pre-entry wick
                # cannot false-trigger a freshly opened position.
                opened = position.opened_at
                if opened is not None and opened.tzinfo is None:
                    opened = opened.replace(tzinfo=UTC)
                candle_start = datetime.fromtimestamp(int(latest["timestamp"]), tz=UTC)
                if opened is None or candle_start >= opened:
                    bar_low = Decimal(str(latest["low"]))
                    bar_high = Decimal(str(latest["high"]))
                    if is_short:
                        if bar_high >= position.stop_loss:
                            stop_hit = True
                        if tp_active and bar_low <= position.take_profit:
                            tp_hit = True
                    else:
                        if bar_low <= position.stop_loss:
                            stop_hit = True
                        if tp_active and bar_high >= position.take_profit:
                            tp_hit = True

                # Evaluate the stop before the take-profit — protect capital first.
                if stop_hit:
                    await self.close_position(position, "stop_loss")
                elif tp_hit:
                    await self.close_position(position, "take_profit")
                else:
                    await self._update_trailing_stop(position, price)
            except Exception as exc:
                self._log(
                    "position_manage_error",
                    f"{position.symbol}: {exc}",
                    LogLevel.error,
                )
                self.db.commit()

    async def close_position(self, position: Position, reason: str, _retry: int = 3) -> Order:
        # Cancel the resting exchange stop before closing — the close order
        # supersedes it. If the stop already triggered (404) the cancel is a
        # no-op; if it is still resting it is removed so it cannot fire on a
        # position we are actively closing (which would double-close or, on
        # spot, attempt to sell more than we hold after the close fills).
        await self._cancel_exchange_stop(position)
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
                        f"\u26a0\ufe0f {position.symbol} close attempt {attempt + 1} failed: {exc}"
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
            f"\U0001f534 CRITICAL: {position.symbol} FAILED to close ({reason}) after {_retry} attempts! "
            f"Manual intervention may be required. Last error: {last_exc}"
        )
        raise last_exc  # type: ignore[misc]

    async def _close_position_inner(
        self, position: Position, reason: str, attempt: int
    ) -> Order:
        signal_time = datetime.now(UTC)
        submission_time = datetime.now(UTC)
        is_short = position.side == OrderSide.sell
        market = get_settings().trading_market.lower()
        close_side = OrderSide.buy if is_short else OrderSide.sell
        # A short can only exist on futures, so it always closes via a reduce-only
        # buy; a long closes on whichever market it was opened on.
        if is_short or market == "futures":
            close_direction = "long" if is_short else "short"
            response = await self.client.place_futures_market_order(
                position.symbol, position.quantity, close_direction, reduce_only=True
            )
            exit_price = Decimal(str(response.get("avg_deal_price") or response.get("fill_price") or position.entry_price))
            filled_qty = position.quantity
        else:
            response = await self.client.place_market_sell(position.symbol, position.quantity)
            exit_price = Decimal(str(response.get("avg_deal_price") or position.entry_price))
            # `filled_total` is QUOTE-denominated; derive the base quantity sold.
            filled_qty = _filled_base_qty(response, exit_price, position.quantity)
        ack_time = datetime.now(UTC)

        fee = _fee_in_quote(response, exit_price, position.symbol)
        # Short PnL is mirrored: profit when exit < entry.
        if is_short:
            pnl = (position.entry_price - exit_price) * filled_qty - fee
        else:
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
            side=close_side,
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
            side=close_side,
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
            side=close_side.value,
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

        # Partial close: the close_position entry cancelled the resting stop,
        # but a residual position remains and still needs exchange-side
        # protection. Re-place the stop at the existing stop_loss for the
        # reduced quantity. (Futures close-only stops are size-agnostic so the
        # re-place is identical; spot re-places with the new smaller base qty.)
        if position.status == PositionStatus.open:
            await self._place_exchange_stop(position)

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

    async def _update_trailing_stop(self, position: Position, price: Decimal) -> None:
        is_short = position.side == OrderSide.sell
        trailing_pct = self._trailing_stop_pct()
        stop_amended = False
        if is_short:
            # Ratchet the stop DOWN as price falls; skip until a new low is made.
            if position.trailing_stop and price >= position.trailing_stop:
                pass
            else:
                new_stop = price * (Decimal("1") + trailing_pct)
                if new_stop < position.stop_loss:
                    position.stop_loss = new_stop
                    position.trailing_stop = new_stop
                    self.db.commit()
                    stop_amended = True
        else:
            if position.trailing_stop and price <= position.trailing_stop:
                return
            new_stop = price * (Decimal("1") - trailing_pct)
            if new_stop > position.stop_loss:
                position.stop_loss = new_stop
                position.trailing_stop = new_stop
                self.db.commit()
                stop_amended = True
        # Breakeven stop: once unrealized profit exceeds the trigger threshold,
        # move stop-loss to entry price so the trade cannot become a loss.
        if not position.breakeven_stop:
            trigger_pct = Decimal(str(get_settings().breakeven_stop_trigger_pct))
            if trigger_pct > 0:
                if is_short:
                    profit_pct = (position.entry_price - price) / position.entry_price
                    at_risk = position.stop_loss > position.entry_price
                else:
                    profit_pct = (price - position.entry_price) / position.entry_price
                    at_risk = position.stop_loss < position.entry_price
                if profit_pct >= trigger_pct and at_risk:
                    position.stop_loss = position.entry_price
                    position.breakeven_stop = True
                    self._log(
                        "breakeven_stop",
                        f"{position.symbol}: stop moved to breakeven ({position.entry_price})",
                    )
                    self.db.commit()
                    stop_amended = True
        # The resting exchange stop must track the new stop level. One amend
        # call covers both a trailing ratchet and a breakeven move (whichever
        # fired this cycle). Skipped when nothing changed.
        if stop_amended:
            await self._amend_exchange_stop(position)

    # ------------------------------------------------------------------
    # Exchange-side stop management
    # ------------------------------------------------------------------

    async def _place_exchange_stop(self, position: Position) -> None:
        """Place a protective stop on the exchange so it rests there.

        Best-effort: on failure the position stays open and the local 15-min
        poll remains the only protection (degraded mode). A failure is logged
        and alerted so the operator can intervene. Idempotent-ish: if a stop
        is already resting (``exchange_stop_order_id`` set) this is a no-op.
        """
        if position.exchange_stop_order_id:
            return
        is_short = position.side == OrderSide.sell
        market = get_settings().trading_market.lower()
        stop_price = position.stop_loss
        try:
            if market == "futures":
                resp = await self.client.place_futures_stop_loss(
                    position.symbol, stop_price, is_short=is_short
                )
            else:
                # Spot shorts cannot exist; this path is long-only.
                resp = await self.client.place_spot_stop_loss(
                    position.symbol, stop_price, base_amount=position.quantity, is_short=is_short
                )
            order_id = str(resp.get("id") or "")
            if not order_id:
                raise RuntimeError(f"exchange returned no stop order id: {resp}")
            position.exchange_stop_order_id = order_id
            position.stop_placed_at = datetime.now(UTC)
            self.db.commit()
            self._log(
                "exchange_stop_placed",
                f"{position.symbol}: exchange stop placed at {stop_price} (id={order_id})",
            )
        except Exception as exc:
            # Critical: the position is untracked-by-exchange-stop. Alert so an
            # operator can place a manual stop. Local polling still guards it.
            self._log(
                "exchange_stop_failed",
                f"{position.symbol}: FAILED to place exchange stop at {stop_price}: {exc}. "
                f"DEGRADED — local poll only. Place a manual stop if needed.",
                LogLevel.error,
            )
            await self.notifier.send(
                f"\u26a0\ufe0f {position.symbol}: exchange stop FAILED ({exc}). "
                f"DEGRADED mode — local poll only. Entry={position.entry_price} stop={stop_price}."
            )
            self.db.commit()

    async def _amend_exchange_stop(self, position: Position) -> None:
        """Amend the resting exchange stop to track ``position.stop_loss``.

        Gate.io has no native amend for conditional orders, so this cancels the
        old stop and re-places a new one at the current stop level. If the
        cancel fails for a reason other than 404 (already triggered), we still
        attempt the re-place: the old stop may have already fired, in which
        case the position is closing/closed and the new stop is harmless. On
        full failure the position falls back to local-poll-only protection.
        """
        old_id = position.exchange_stop_order_id
        is_short = position.side == OrderSide.sell
        market = get_settings().trading_market.lower()
        stop_price = position.stop_loss
        if not old_id:
            # No resting stop — try to place one (covers positions opened in
            # degraded mode whose exchange placement failed at entry time).
            await self._place_exchange_stop(position)
            return
        # Cancel the existing stop first.
        try:
            if market == "futures":
                await self.client.cancel_futures_conditional_order(old_id)
            else:
                await self.client.cancel_spot_price_order(old_id)
        except Exception as exc:
            self._log(
                "exchange_stop_amend_cancel_failed",
                f"{position.symbol}: cancel of old stop {old_id} failed ({exc}); "
                f"attempting re-place anyway",
                LogLevel.warning,
            )
        # Re-place at the new stop level.
        try:
            if market == "futures":
                resp = await self.client.place_futures_stop_loss(
                    position.symbol, stop_price, is_short=is_short
                )
            else:
                resp = await self.client.place_spot_stop_loss(
                    position.symbol, stop_price, base_amount=position.quantity, is_short=is_short
                )
            new_id = str(resp.get("id") or "")
            if not new_id:
                raise RuntimeError(f"exchange returned no stop order id: {resp}")
            position.exchange_stop_order_id = new_id
            position.stop_placed_at = datetime.now(UTC)
            self.db.commit()
            self._log(
                "exchange_stop_amended",
                f"{position.symbol}: exchange stop amended to {stop_price} "
                f"(old={old_id} new={new_id})",
            )
        except Exception as exc:
            # Re-place failed — the position may now have NO resting exchange
            # stop. Clear the id so a later amend retry can re-place from scratch.
            position.exchange_stop_order_id = None
            position.stop_placed_at = None
            self.db.commit()
            self._log(
                "exchange_stop_amend_failed",
                f"{position.symbol}: FAILED to re-place exchange stop at {stop_price}: {exc}. "
                f"DEGRADED — local poll only.",
                LogLevel.error,
            )
            await self.notifier.send(
                f"\u26a0\ufe0f {position.symbol}: exchange stop amend FAILED ({exc}). "
                f"DEGRADED mode. stop={stop_price}."
            )

    async def _cancel_exchange_stop(self, position: Position) -> None:
        """Cancel the resting exchange stop. Used when the position is closed
        (the close order supersedes the stop) or when the stop has already
        triggered (404 is expected and swallowed)."""
        order_id = position.exchange_stop_order_id
        if not order_id:
            return
        market = get_settings().trading_market.lower()
        try:
            if market == "futures":
                await self.client.cancel_futures_conditional_order(order_id)
            else:
                await self.client.cancel_spot_price_order(order_id)
            self._log(
                "exchange_stop_cancelled",
                f"{position.symbol}: exchange stop {order_id} cancelled on close",
            )
        except Exception as exc:
            # 404 is expected (stop already fired or was cancelled). Other
            # errors are non-fatal at this point — the position is closing.
            self._log(
                "exchange_stop_cancel_failed",
                f"{position.symbol}: cancel of stop {order_id} on close failed ({exc})",
                LogLevel.warning,
            )
        position.exchange_stop_order_id = None
        position.stop_placed_at = None
        self.db.commit()

    async def _check_liquidation_risk(self, position: Position, price: Decimal) -> bool:
        """Liquidation-distance guard for futures positions.

        Reads back the exchange's liquidation price and force-closes the
        position when the mark price is within ``futures_liq_warning_pct`` of
        it — BEFORE the exchange's liquidation engine fires. This defends
        against a fast adverse move that gaps through the (15-min-polled) ATR
        stop. Spot positions and a disabled guard return False (no action).

        Returns True when the position was force-closed (caller should skip the
        rest of the cycle for it), False otherwise.
        """
        _settings = get_settings()
        if _settings.trading_market.lower() != "futures":
            return False
        warn_pct = Decimal(str(_settings.futures_liq_warning_pct))
        if warn_pct <= 0:
            return False
        try:
            fut_pos = await self.client.get_futures_position(position.symbol)
        except Exception as exc:
            # Best-effort: a failed read-back must not abort stop management.
            self._log(
                "liq_check_failed",
                f"{position.symbol}: liquidation-price read-back failed ({exc})",
                LogLevel.warning,
            )
            return False
        if not fut_pos:
            return False
        liq_raw = fut_pos.get("liquidation_price")
        if liq_raw in (None, "", "0"):
            return False  # no liquidation price (cross-margin or flat)
        liq_price = Decimal(str(liq_raw))
        if liq_price <= 0:
            return False
        is_short = position.side == OrderSide.sell
        # Long: liquidation sits BELOW price; distance = (price - liq) / price.
        # Short: liquidation sits ABOVE price; distance = (liq - price) / price.
        if is_short:
            distance = (liq_price - price) / price
        else:
            distance = (price - liq_price) / price
        if distance > warn_pct:
            return False
        # Within the warning band — close before liquidation. The exchange stop
        # may not have fired yet (it rests at the ATR stop, not the liq price),
        # so an explicit close is required.
        self._log(
            "liquidation_warning",
            f"{position.symbol}: mark {price} within {distance:.4%} of liquidation "
            f"{liq_price} (warn {warn_pct:.2%}) — force-closing",
            LogLevel.error,
        )
        await self.notifier.send(
            f"\U0001f534 LIQUIDATION RISK {position.symbol}: mark={price} liq={liq_price} "
            f"distance={distance:.4%} < {warn_pct:.2%}. Force-closing before liquidation."
        )
        try:
            await self.close_position(position, "liquidation_warning")
        except Exception as exc:
            self._log(
                "liquidation_close_failed",
                f"{position.symbol}: force-close on liquidation warning failed ({exc})",
                LogLevel.error,
            )
            self.db.commit()
        return True

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
