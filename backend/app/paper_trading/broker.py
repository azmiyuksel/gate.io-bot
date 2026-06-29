import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import PaperAccount, PaperLog, PaperOrder, PaperPosition, PaperTrade
from app.models.enums import (
    LogLevel,
    OrderSide,
    PaperOrderStatus,
    PaperOrderType,
    PaperPositionMode,
    PaperPositionSide,
    PaperTimeInForce,
)
from app.paper_trading.execution_simulator import ExecutionSimulator
from app.paper_trading.models import MarketData, PaperExecution, PaperSide, TradingSignal

logger = logging.getLogger(__name__)


def _tif_value(tif) -> str:
    """Defensive accessor — SQLAlchemy may materialise a python StrEnum as either
    enum or raw ``str`` depending on the dialect/driver. Normalise to the TIF
    code string ("GTC" / "IOC" / "FOK" / "POST")."""
    if tif is None:
        return "GTC"
    if hasattr(tif, "value"):
        return tif.value
    return str(tif)


# Cache real Gate.io funding rates for ~5 minutes so the engine doesn't hit the
# REST endpoint on every accident-prone funding-tick for every position.
_FUNDING_CACHE: dict[str, tuple[float, datetime]] = {}
_FUNDING_CACHE_TTL = timedelta(minutes=5)


class PaperBroker:
    def __init__(self, db: Session, account: PaperAccount, simulator: ExecutionSimulator | None = None) -> None:
        from app.core.config import get_settings
        from app.paper_trading.mirror import resolve_paper_exec

        self.db = db
        self.account = account
        self.exec = resolve_paper_exec(db, get_settings())
        if simulator is None:
            # Fees follow the mirrored market (spot vs futures) so paper drag
            # matches what is actually paid live. Depth/impact knobs come from
            # settings so they can be calibrated per-deployment (the legacy
            # symbol-agnostic 2% cap / 5000 USDT floor made alts look
            # unrealistically liquid during volatility).
            settings = get_settings()
            simulator = ExecutionSimulator(
                maker_fee=float(self.exec.maker_fee), taker_fee=float(self.exec.taker_fee),
                max_impact=getattr(settings, "paper_max_impact", 0.02),
                min_depth=getattr(settings, "paper_min_depth", 5_000.0),
                impact_coef=getattr(settings, "paper_impact_coef", 0.001),
                depth_fraction=getattr(settings, "paper_depth_fraction", 0.05),
            )
        self.simulator = simulator

    # ───────────────────────────── signals (legacy entry) ────────────────

    async def submit_signal(self, signal: TradingSignal, quantity: Decimal, data: MarketData) -> PaperOrder:
        """Submit a strategy SIGNAL as a market order (legacy entry path).

        Kept async for parity with ``submit_order`` — the latency window is
        awaited so the signal-to-fill gap mirrors a live execution pipeline.
        Applies the same lot-step rounding + min-notional gate as
        ``submit_order`` so legacy market entries respect contract sizes.
        """
        signal_time = signal.timestamp
        submission_time = datetime.now(UTC)
        # Lot-step rounding + min-notional gate (parity with submit_order).
        qty = self._round_quantity(quantity)
        if qty <= 0:
            from app.core.config import get_settings

            settings = get_settings()
            order = PaperOrder(
                account_id=self.account.id, symbol=signal.symbol,
                side=OrderSide(signal.side.value), order_type=PaperOrderType.market,
                status=PaperOrderStatus.rejected, requested_quantity=quantity,
                signal={"reason": "quantity_below_step", "strategy": signal.strategy},
            )
            self.db.add(order)
            self.db.commit()
            self._log("order_rejected", f"{signal.symbol}: quantity_below_step")
            return order
        mid = Decimal(str(data.price)) if data.price > 0 else Decimal("0")
        if mid > 0:
            from app.core.config import get_settings

            settings = get_settings()
            if (qty * mid) < Decimal(str(settings.paper_min_notional)):
                order = PaperOrder(
                    account_id=self.account.id, symbol=signal.symbol,
                    side=OrderSide(signal.side.value), order_type=PaperOrderType.market,
                    status=PaperOrderStatus.rejected, requested_quantity=quantity,
                    signal={"reason": "min_notional", "strategy": signal.strategy},
                )
                self.db.add(order)
                self.db.commit()
                self._log("order_rejected", f"{signal.symbol}: min_notional")
                return order
        order = PaperOrder(
            account_id=self.account.id,
            symbol=signal.symbol,
            side=OrderSide(signal.side.value),
            order_type=PaperOrderType.market,
            status=PaperOrderStatus.pending,
            requested_quantity=qty,
            time_in_force=PaperTimeInForce.ioc,  # market entries drop partials
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
        await self._execute_order(order, data, signal_time=signal_time, submission_time=submission_time)
        return order

    # ───────────────────────────── generic order API ─────────────────────

    async def submit_order(
        self,
        *,
        symbol: str,
        side: PaperSide,
        quantity: Decimal,
        order_type: PaperOrderType,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        take_profit: Decimal | None = None,
        time_in_force: PaperTimeInForce = PaperTimeInForce.gtc,
        post_only: bool = False,
        reduce_only: bool = False,
        position_side: PaperPositionSide | None = None,
        signal: dict | None = None,
        data: MarketData | None = None,
    ) -> PaperOrder:
        """Generic order submission supporting market / limit / stop / stop_limit / OCO.

        For market and post-only-cross orders, the engine awaits the latency
        window before applying the fill. For limit / stop orders, the order
        rests in the DB (``status=pending``) and the engine tick loop processes
        it as the market trades through the trigger prices.
        """
        # Notional / min-qty check: reject dust orders like the live exchange.
        from app.core.config import get_settings

        settings = get_settings()
        qty = self._round_quantity(quantity)
        if qty <= 0:
            order = self._create_rejected_order(symbol, side, quantity, order_type, "quantity_below_step", signal, price, stop_price)
            self.db.add(order)
            self.db.commit()
            return order
        mid = Decimal(str(data.price)) if data else Decimal("0")
        if mid > 0 and (qty * mid) < Decimal(str(settings.paper_min_notional)):
            order = self._create_rejected_order(symbol, side, quantity, order_type, "min_notional", signal, price, stop_price)
            self.db.add(order)
            self.db.commit()
            return order

        # OCO: create two linked resting orders (TP = limit, SL = stop-limit),
        # both reduce-only. The first to fill cancels the other via
        # ``linked_order_id``.
        if order_type == PaperOrderType.oco:
            if take_profit is None or stop_price is None:
                order = self._create_rejected_order(symbol, side, quantity, order_type, "oco_requires_tp_and_stop", signal, price, stop_price)
                self.db.add(order)
                self.db.commit()
                return order
            tp_order = PaperOrder(
                account_id=self.account.id, symbol=symbol,
                side=OrderSide(side.value),
                order_type=PaperOrderType.limit,
                status=PaperOrderStatus.pending,
                requested_quantity=qty, filled_quantity=Decimal("0"),
                limit_price=take_profit, stop_price=None,
                time_in_force=time_in_force, post_only=post_only, reduce_only=True,
                position_side=position_side, signal=signal or {},
            )
            sl_order = PaperOrder(
                account_id=self.account.id, symbol=symbol,
                side=OrderSide(side.value),
                order_type=PaperOrderType.stop_limit,
                status=PaperOrderStatus.pending,
                requested_quantity=qty, filled_quantity=Decimal("0"),
                limit_price=price, stop_price=stop_price,
                time_in_force=time_in_force, post_only=False, reduce_only=True,
                position_side=position_side, signal=signal or {},
            )
            self.db.add_all([tp_order, sl_order])
            self.db.commit()
            self.db.refresh(tp_order)
            self.db.refresh(sl_order)
            tp_order.linked_order_id = sl_order.id
            sl_order.linked_order_id = tp_order.id
            self.db.commit()
            self._log("oco_placed", f"{symbol} TP@{take_profit} SL@stop={stop_price} qty={qty}")
            return tp_order

        order = PaperOrder(
            account_id=self.account.id, symbol=symbol,
            side=OrderSide(side.value),
            order_type=order_type,
            status=PaperOrderStatus.pending,
            requested_quantity=qty, filled_quantity=Decimal("0"),
            limit_price=price, stop_price=stop_price,
            time_in_force=time_in_force, post_only=post_only, reduce_only=reduce_only,
            position_side=position_side,
            signal=signal or {},
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        # Market (and POST-only market-corner) orders fill immediately. Limit /
        # stop / stop_limit rest until the tick loop processes them.
        if order_type == PaperOrderType.market:
            if post_only:
                # A market post-only order is a semantic contradiction; route it
                # to the limit path using the current last price as a fallback.
                order.order_type = PaperOrderType.limit
                order.limit_price = mid if mid > 0 else order.limit_price
                self.db.commit()
                return order
            await self._execute_order(order, data)
        return order

    # ───────────────────────────── fill path ─────────────────────────────

    async def _execute_order(
        self,
        order: PaperOrder,
        data: MarketData,
        *,
        signal_time: datetime | None = None,
        submission_time: datetime | None = None,
    ) -> None:
        """Drive the (now awaited) market-fill latency, then apply the execution."""
        signal_time = signal_time or datetime.now(UTC)
        submission_time = submission_time or datetime.now(UTC)
        # order.side may be either an OrderSide enum or a string ("buy"/"sell").
        side = PaperSide(order.side.value if hasattr(order.side, "value") else order.side)
        # Generate the execution FIRST so we know how long to sleep (latency is
        # drawn inside the simulator). We then await that latency, simulating
        # the signal-to-fill race against market movement, before applying it.
        execution = self.simulator.execute_market(
            order.id, side, float(order.requested_quantity), data,
            time_in_force=_tif_value(order.time_in_force),
        )
        if execution.latency_ms > 0:
            await asyncio.sleep(execution.latency_ms / 1000.0)
        self.apply_execution(order, execution, data)
        await self._record_execution_quality(order, execution, signal_time, submission_time)

    async def fill_limit_order(self, order: PaperOrder, data: MarketData) -> bool:
        """Attempt to fill a resting limit / stop-limit order on a tick.

        Returns True if the order reached a terminal state (filled / cancelled),
        False if it should keep resting. Handles OCO cancellation of the
        linked sibling on fill.
        """
        if order.status in (PaperOrderStatus.filled, PaperOrderStatus.cancelled, PaperOrderStatus.rejected):
            return True
        if order.limit_price is None:
            return False
        side = PaperSide(order.side.value if hasattr(order.side, "value") else order.side)
        execution = self.simulator.execute_limit(
            order.id, side, float(order.requested_quantity),
            float(order.limit_price), data,
            time_in_force=_tif_value(order.time_in_force),
            post_only=bool(order.post_only),
        )
        if execution is None:
            # Still resting. No state change.
            return False
        if execution.filled_quantity <= 0 and execution.reason in (
            "post_only_would_cross", "ioc_not_crossed", "fok_not_crossed", "fok_queue_partial", "ioc_partial",
        ):
            # Cancel terminal reasons that came back with zero fill.
            order.status = PaperOrderStatus.cancelled
            order.filled_at = datetime.now(UTC)
            self.db.commit()
            self._log("order_cancelled", f"{order.symbol} {order.order_type} {execution.reason}")
            self._cancel_linked(order)
            return True
        if execution.filled_quantity <= 0:
            return False
        # Apply the fill.
        await asyncio.sleep(execution.latency_ms / 1000.0)
        self.apply_execution(order, execution, data, reduce_only=bool(order.reduce_only))
        await self._record_execution_quality(order, execution, datetime.now(UTC), datetime.now(UTC))
        if order.status == PaperOrderStatus.filled:
            self._cancel_linked(order)
        return True

    def check_stop_trigger(self, order: PaperOrder, data: MarketData) -> bool:
        """Check if a stop / stop-limit order triggers on a tick."""
        if order.stop_price is None:
            return False
        side = PaperSide(order.side.value if hasattr(order.side, "value") else order.side)
        return self.simulator.execute_stop(
            order.id, side, float(order.requested_quantity), float(order.stop_price), data,
        )

    async def trigger_stop_order(self, order: PaperOrder, data: MarketData) -> None:
        """Convert a triggered stop order to a market/limit fill on the spot."""
        # Once triggered, a stop order behaves like a market; a stop-limit
        # behaves like a (resting) limit. We just route through the market fill
        # path for simplicity (stop-limit would need the limit fill loop).
        if order.order_type == PaperOrderType.stop_limit and order.limit_price is not None:
            # Re-classify as a limit order and let the tick loop fill it.
            order.limit_price = order.limit_price
            self.db.commit()
            return
        await self._execute_order(order, data)

    def _cancel_linked(self, order: PaperOrder) -> None:
        if order.linked_order_id is None:
            return
        linked = self.db.get(PaperOrder, order.linked_order_id)
        if linked and linked.status not in (PaperOrderStatus.filled, PaperOrderStatus.cancelled, PaperOrderStatus.rejected):
            linked.status = PaperOrderStatus.cancelled
            linked.filled_at = datetime.now(UTC)
            self.db.commit()
            self._log("oco_cancel", f"{linked.symbol} cancelled (sibling filled/cancelled)")

    def cancel_order(self, order: PaperOrder) -> None:
        if order.status in (PaperOrderStatus.filled, PaperOrderStatus.cancelled, PaperOrderStatus.rejected):
            return
        order.status = PaperOrderStatus.cancelled
        order.filled_at = datetime.now(UTC)
        self.db.commit()
        self._log("order_cancelled", f"{order.symbol} {order.order_type} cancelled by user")
        self._cancel_linked(order)

    def apply_execution(
        self,
        order: PaperOrder,
        execution: PaperExecution,
        data: MarketData | None = None,
        *,
        reduce_only: bool = False,
    ) -> None:
        # Apply min-notional rejection at fill-time too (covers tiny partials).
        order.filled_quantity = Decimal(str(execution.filled_quantity))
        order.average_fill_price = Decimal(str(execution.average_price))
        order.fee_paid = Decimal(str(execution.fee))
        order.latency_ms = execution.latency_ms
        if execution.filled_quantity <= 0:
            order.status = PaperOrderStatus.rejected
            self._log("order_rejected", f"{order.symbol} {execution.reason}")
            return
        order.status = PaperOrderStatus.partially_filled if execution.partial else PaperOrderStatus.filled
        order.filled_at = datetime.now(UTC)
        if execution.side == PaperSide.buy:
            self._apply_buy(order, execution, reduce_only=reduce_only)
        else:
            self._apply_sell(order, execution, reduce_only=reduce_only)
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
        self._log("order_filled", f"{order.side} {order.symbol} qty={execution.filled_quantity} reason={execution.reason}")

    def _stop_tp_params(self) -> tuple[Decimal, Decimal]:
        """(ATR stop multiplier, take-profit reward:risk) — shared by long/short
        opens and by the engine's position sizing so the stop the trade is sized
        against is the stop actually placed. Mirrors the live StrategySettings
        when paper_mirror_live is on."""
        return self.exec.atr_stop_multiplier, self.exec.tp_rr

    def round_trip_fee_fraction(self) -> Decimal:
        """Round-trip fee as a fraction of notional, derived from the ACTUAL fee
        schedule (maker + taker) — used by the engine for breakeven-stop placement
        so the "stop at breakeven incl. fees" stop sits at the true fee band
        instead of a stale hard-coded 0.002 assumption that drifts when the fee
        schedule is reconfigured.

        Conservative: assumes the WORST case (entry taker + exit taker). The
        live engine always enters market taker; trend-following strategies exit
        via trailing stop (also market => taker), so the worst-case fee band is
        the right protection width for the breakeven stop.
        """
        return Decimal(str(self.exec.taker_fee)) + Decimal(str(self.exec.taker_fee))

    def _fits_free_margin(self, notional: Decimal) -> bool:
        """A new long's notional must fit within free margin (equity * leverage)
        minus the notional already committed to open positions. Mirroring a spot
        live account, leverage is 1 so notional must fit within equity."""
        from app.paper_trading.portfolio import PaperPortfolio

        portfolio = PaperPortfolio(self.db, self.account)
        equity = portfolio.equity()
        if equity <= 0:
            return False
        leverage = self.exec.leverage
        used = sum(p.quantity * p.last_price for p in portfolio.open_positions())
        return (used + notional) <= equity * leverage

    def _funding_cost(self, position: PaperPosition, close_qty: Decimal, exit_time: datetime) -> Decimal:
        """Pro-rata financing carry on the closed notional FROM the last funding
        settlement timestamp to exit, charged at the in-force funding rate.

        Disabled for spot (no funding). When funding accrual has already settled
        periodically via ``accrue_funding`` (which mutates equity every 8h), this
        only charges the residual hold period since the last settlement so we
        do NOT double-count funding.
        """
        from app.core.config import get_settings

        settings = get_settings()
        if not self.exec.funding_enabled or settings.funding_daily_rate_pct <= 0:
            return Decimal("0")
        opened = position.last_funding_ts or position.opened_at
        if opened is None:
            return Decimal("0")
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=UTC)
        held_seconds = (exit_time - opened).total_seconds()
        if held_seconds <= 0:
            return Decimal("0")
        held_days = Decimal(str(held_seconds / 86_400.0))
        # Use the in-force signed rate cached on the position (accrual updates it).
        # If unset (legacy position), fall back to the conservative flat daily rate.
        rate = position.last_funding_rate if position.last_funding_rate is not None else Decimal(
            str(settings.funding_daily_rate_pct)
        )
        # Funding is signed: positive => long pays short, negative => short pays long.
        # Use the position's signed side to determine cash direction.
        is_short = (position.position_side == PaperPositionSide.short) or (
            position.position_side is None and position.side == "sell"
        )
        cost = position.average_entry_price * close_qty * abs(rate) * held_days
        # Add as an unsigned cost to PnL — sign-flipping of cash happens in accrue_funding.
        # For the close PnL deduction we apply a cost (long+rate>0 => cost; short+rate<0=>cost).
        positive_rate = rate > 0
        long_pays = positive_rate
        short_pays = not positive_rate
        if (not is_short and long_pays) or (is_short and short_pays):
            return cost
        return -cost  # favorable funding rebate

    async def accrue_funding(self, position: PaperPosition, now: datetime) -> None:
        """Signed 8-hourly funding accrual: longs pay shorts when rate > 0.

        Mutates ``cash_balance`` and records a funding-settlement paper log. The
        in-force rate is fetched (and cached for ~5 min) from the live exchange
        so long-duration carries surface their real signed carry cost in equity
        rather than being charged once at close.
        """
        from app.core.config import get_settings

        settings = get_settings()
        if not self.exec.funding_enabled or settings.paper_funding_interval_hours <= 0:
            return
        last = position.last_funding_ts or position.opened_at
        if last is None:
            position.last_funding_ts = now
            self.db.commit()
            return
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        interval = timedelta(hours=int(settings.paper_funding_interval_hours))
        if (now - last) < interval:
            return
        # Don't compound multiple settlements in one tick — only one accrual.
        intervals_due = int((now - last) / interval)
        if intervals_due <= 0:
            return
        rate = await self._fetch_signed_funding_rate(position.symbol)
        position.last_funding_rate = Decimal(str(rate))
        # The funding notional is the position's mark value at settle time.
        mark_value = position.quantity * (position.mark_price or position.last_price or position.average_entry_price)
        notional_per_interval = mark_value * abs(Decimal(str(rate)))
        # Sign: long pays short when rate > 0 => long's cash decreases, short's
        # cash increases. For rate < 0 the reverse.
        is_short = (position.position_side == PaperPositionSide.short) or (
            position.position_side is None and position.side == "sell"
        )
        if rate > 0:
            cash_delta = -notional_per_interval if not is_short else +notional_per_interval
        else:
            cash_delta = +notional_per_interval if not is_short else -notional_per_interval
        cash_delta *= intervals_due
        self.account.cash_balance += cash_delta
        position.last_funding_ts = last + intervals_due * interval
        self.db.commit()
        self._log(
            "funding_settlement",
            f"{position.symbol} rate={rate:.6f} intervals={intervals_due} cash_delta={cash_delta}",
            {"symbol": position.symbol, "rate": rate, "intervals": intervals_due, "cash_delta": str(cash_delta)},
        )

    async def _fetch_signed_funding_rate(self, symbol: str) -> float:
        """Fetch the current signed funding rate, cached for 5 min per symbol."""
        global _FUNDING_CACHE
        now = datetime.now(UTC)
        cached = _FUNDING_CACHE.get(symbol)
        if cached and (now - cached[1]) < _FUNDING_CACHE_TTL:
            return cached[0]
        try:
            from app.services.exchange.gateio import GateIOClient

            client = GateIOClient()
            try:
                data = await client.get_futures_funding_rate(symbol)
                if data and data.get("r") not in (None, ""):
                    rate = float(data["r"])
                    _FUNDING_CACHE[symbol] = (rate, now)
                    return rate
            finally:
                await client.close()
        except Exception:
            logger.warning("paper funding: failed to fetch rate for %s", symbol, exc_info=True)
        # Fall back to the conservative flat daily rate as a signed-positive rate.
        from app.core.config import get_settings

        return float(get_settings().funding_daily_rate_pct)

    def open_liquidation_check(self, position: PaperPosition, mark: Decimal) -> bool:
        """Return True when the position's mark crosses the maintenance margin.

        Single-tier liquidation: when a leveraged position's unrealized loss
        consumes `(1 - paper_maintenance_margin_pct) * initial_margin`, the
        exchange would force-close it. Cheap computed at any mark-tick by the
        engine.
        """
        from app.core.config import get_settings

        if position.leverage is None or position.leverage <= 1:
            return False
        initial_margin = position.margin or (position.average_entry_price * position.quantity / position.leverage)
        if initial_margin <= 0:
            return False
        maint = Decimal(str(get_settings().paper_maintenance_margin_pct))
        is_short = (position.position_side == PaperPositionSide.short) or (
            position.position_side is None and position.side == "sell"
        )
        # Mark PnL: long loses when mark<entry; short loses when mark>entry.
        if is_short:
            unrealized = (position.average_entry_price - mark) * position.quantity
        else:
            unrealized = (mark - position.average_entry_price) * position.quantity
        # Liquidation trigger: unrealized loss exceeds (1 - maintenance) * margin.
        return unrealized <= -(initial_margin * (Decimal("1") - maint))

    def compute_liquidation_price(self, position: PaperPosition) -> Decimal | None:
        """Compute the mark price at which the position liquidates."""
        from app.core.config import get_settings

        if position.leverage is None or position.leverage <= 1:
            return None
        initial_margin = position.margin or (position.average_entry_price * position.quantity / position.leverage)
        if initial_margin <= 0:
            return None
        maint = Decimal(str(get_settings().paper_maintenance_margin_pct))
        loss_at_liq = initial_margin * (Decimal("1") - maint)
        is_short = (position.position_side == PaperPositionSide.short) or (
            position.position_side is None and position.side == "sell"
        )
        # long: loss = (entry - mark) * qty => mark = entry - loss/qty
        # short: loss = (mark - entry) * qty => mark = entry + loss/qty
        per_unit_loss = loss_at_liq / position.quantity
        if is_short:
            return position.average_entry_price + per_unit_loss
        return position.average_entry_price - per_unit_loss

    async def close_position(
        self,
        position: PaperPosition,
        data: MarketData,
        reason: str,
        quantity: Decimal | None = None,
        *,
        force_liquidation: bool = False,
    ) -> None:
        now = datetime.now(UTC)
        close_qty = quantity if quantity is not None and quantity < position.quantity else position.quantity
        is_short = position.side == "sell"
        close_side = OrderSide.buy if is_short else OrderSide.sell
        exit_sim_side = PaperSide.buy if is_short else PaperSide.sell

        order = PaperOrder(
            account_id=self.account.id,
            symbol=position.symbol,
            side=close_side,
            order_type=PaperOrderType.market,
            status=PaperOrderStatus.filled,
            requested_quantity=close_qty,
            filled_quantity=close_qty,
            time_in_force=PaperTimeInForce.ioc,
            reduce_only=True,
            position_side=position.position_side,
            signal={"reason": reason, "type": "partial" if close_qty < position.quantity else "exit", "liquidation": force_liquidation},
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        execution = self.simulator.execute_market(
            order_id=order.id,
            side=exit_sim_side,
            quantity=float(close_qty),
            data=data,
            time_in_force="IOC",
        )
        if execution.latency_ms > 0:
            await asyncio.sleep(execution.latency_ms / 1000.0)
        order.filled_quantity = Decimal(str(execution.filled_quantity))
        order.average_fill_price = Decimal(str(execution.average_price))
        order.fee_paid = Decimal(str(execution.fee))
        order.latency_ms = execution.latency_ms
        order.filled_at = now
        exit_price = Decimal(str(execution.average_price))
        if is_short:
            pnl = (position.average_entry_price - exit_price) * close_qty - Decimal(str(execution.fee))
        else:
            pnl = (exit_price - position.average_entry_price) * close_qty - Decimal(str(execution.fee))
        # Pro-rata funding from the last settlement (already-charged periodic
        # accruals are NOT double-counted here). Apply as a signed cost/rebate.
        pnl -= self._funding_cost(position, close_qty, now)

        # LIQUIDATION CAP: the realized loss cannot exceed the posted margin.
        # Real exchanges close at maintenance and the leftover margin is
        # returned (or, in extreme gaps, the insurance fund eats the
        # remainder). Cap pnl at -margin so equity never goes unboundedly
        # negative for a single leveraged loser.
        if force_liquidation and position.margin is not None and position.leverage and position.leverage > 1:
            max_loss = position.margin
            if pnl < -max_loss:
                pnl = -max_loss

        entry_notional = position.average_entry_price * close_qty
        if is_short:
            self.account.cash_balance += pnl - entry_notional
        else:
            self.account.cash_balance += pnl + entry_notional
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
            from app.core.config import get_settings
            eq_engine = ExecutionQualityEngine(self.db)
            exec_order = eq_engine.record_order(
                strategy_name=str(get_settings().live_strategy),
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
                ack_time=ack_time,
            )
        except Exception:
            logger.warning("Paper execution-quality recording failed", exc_info=True)

    # ───────────────────────────── reduce/cross-open positions ─────────

    def _matching_position(self, account_id: int, symbol: str, order_side_buy: bool) -> PaperPosition | None:
        """Find a position to reduce / flip on the same symbol.

        ``order_side_buy`` is the ORDER's side (True = buy order, False = sell).

        - Hedge mode: only reduces the SAME position-side the order targets —
          a buy order reduces a SHORT (``side=sell``), a sell order reduces a
          LONG (``side=buy``). A contrary signal opens a NEW opposing position.
        - One-way: the symmetric behaviour — a sell order reduces the long,
          a buy order reduces the short. The "flip" path closes first.
        """
        # Reduce target side: buy order => shorts (sell) reduced; sell order =>
        # longs (buy) reduced.
        target_side = "sell" if order_side_buy else "buy"
        mode = self.account.position_mode or PaperPositionMode.one_way
        if mode == PaperPositionMode.hedge:
            return (
                self.db.query(PaperPosition)
                .filter(
                    PaperPosition.account_id == account_id,
                    PaperPosition.symbol == symbol,
                    PaperPosition.is_open.is_(True),
                    PaperPosition.side == target_side,
                )
                .first()
            )
        # one-way: same reduce target. The "flip then open residual" callers
        # (non-reduce_only) invoke us to close the opposite side, which is the
        # reduce target here too.
        return (
            self.db.query(PaperPosition)
            .filter(
                PaperPosition.account_id == account_id,
                PaperPosition.symbol == symbol,
                PaperPosition.is_open.is_(True),
                PaperPosition.side == target_side,
            )
            .first()
        )

    def _apply_buy(self, order: PaperOrder, execution: PaperExecution, *, reduce_only: bool = False) -> None:
        quantity = Decimal(str(execution.filled_quantity))
        price = Decimal(str(execution.average_price))
        fee = Decimal(str(execution.fee))
        mode = self.account.position_mode or PaperPositionMode.one_way

        if reduce_only:
            # Reduce ONLY exists by closing an opposite-side (short) position.
            # A BUY order reduces a SHORT: pass order_side_buy=True.
            short_pos = self._matching_position(self.account.id, order.symbol, order_side_buy=True)
            if short_pos is None:
                order.status = PaperOrderStatus.rejected
                self._log("order_rejected", "reduce_only: no opposite position to reduce")
                return
            from app.paper_trading.models import MarketData as _MD
            close_qty = min(quantity, short_pos.quantity)
            self.close_position_sync(
                short_pos,
                _MD(order.symbol, datetime.now(UTC), float(price)),
                "reduce_only",
                quantity=close_qty,
            )
            return

        total_cost = quantity * price + fee
        # Only one-way mode flips the opposite side; hedge mode opens fresh.
        # A BUY order flips a SHORT: find the short (order_side_buy=True => sell).
        existing_short = self._matching_position(self.account.id, order.symbol, order_side_buy=True)
        if existing_short and mode != PaperPositionMode.hedge and existing_short.side == "sell":
            cover_qty = min(quantity, existing_short.quantity)
            self.close_position_sync(
                existing_short,
                MarketData(order.symbol, datetime.now(UTC), float(price)),
                "signal_cover",
                quantity=cover_qty,
            )
            if cover_qty < quantity:
                quantity -= cover_qty
                total_cost = quantity * price + Decimal(str(execution.fee)) * (
                    quantity / (cover_qty + quantity)
                )
            else:
                return

        if not self._fits_free_margin(quantity * price):
            order.status = PaperOrderStatus.rejected
            self._log("order_rejected", "exceeds free margin (leverage cap)")
            return
        self.account.cash_balance -= total_cost
        # Find existing LONG to add to (same side only; hedge mode keeps both
        # sides and matches by position_side).
        if mode == PaperPositionMode.hedge:
            side_filter = "buy"
        else:
            side_filter = "buy"
        existing = (
            self.db.query(PaperPosition)
            .filter(
                PaperPosition.account_id == self.account.id,
                PaperPosition.symbol == order.symbol,
                PaperPosition.is_open.is_(True),
                PaperPosition.side == side_filter,
            )
            .first()
        )
        # Set up leverage/margin for a new position.
        leverage = self.exec.leverage if self.exec.market == "futures" else Decimal("1")
        margin = (quantity * price) / leverage if leverage > 0 else (quantity * price)
        if existing:
            total_qty = existing.quantity + quantity
            existing.average_entry_price = (
                (existing.average_entry_price * existing.quantity) + (price * quantity)
            ) / total_qty
            existing.quantity = total_qty
            existing.last_price = price
            existing.margin = (existing.margin or Decimal("0")) + margin
            existing.leverage = leverage
            existing.liquidation_price = self.compute_liquidation_price(existing)
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
            liq_price = self.compute_liquidation_price_for(price, quantity, leverage, PaperPositionSide.long)
            self.db.add(
                PaperPosition(
                    account_id=self.account.id,
                    symbol=order.symbol,
                    side="buy",
                    quantity=quantity,
                    average_entry_price=price,
                    last_price=price,
                    mark_price=price,
                    stop_loss=stop_loss,
                    initial_stop_loss=stop_loss,
                    take_profit=take_profit,
                    trailing_stop=stop_loss,
                    highest_price=price,
                    breakeven_triggered=False,
                    leverage=leverage,
                    margin=margin,
                    liquidation_price=liq_price,
                    position_side=PaperPositionSide.long if mode == PaperPositionMode.hedge else None,
                    last_funding_ts=datetime.now(UTC) if self.exec.funding_enabled else None,
                )
            )

    def _apply_sell(self, order: PaperOrder, execution: PaperExecution, *, reduce_only: bool = False) -> None:
        quantity = Decimal(str(execution.filled_quantity))
        price = Decimal(str(execution.average_price))
        fee = Decimal(str(execution.fee))
        mode = self.account.position_mode or PaperPositionMode.one_way

        if reduce_only:
            # Reduce ONLY exists by closing an opposite-side (long) position.
            # A SELL order reduces a LONG: pass order_side_buy=False.
            long_pos = self._matching_position(self.account.id, order.symbol, order_side_buy=False)
            if long_pos is None:
                order.status = PaperOrderStatus.rejected
                self._log("order_rejected", "reduce_only: no opposite position to reduce")
                return
            from app.paper_trading.models import MarketData as _MD
            close_qty = min(quantity, long_pos.quantity)
            self.close_position_sync(
                long_pos,
                _MD(order.symbol, datetime.now(UTC), float(price)),
                "reduce_only",
                quantity=close_qty,
            )
            return

        # Close long first in one-way mode. A SELL order flips a LONG: find the
        # long (order_side_buy=False => buy).
        existing_long = self._matching_position(self.account.id, order.symbol, order_side_buy=False)
        if existing_long and mode != PaperPositionMode.hedge and existing_long.side == "buy":
            close_qty = min(quantity, existing_long.quantity)
            self.close_position_sync(
                existing_long,
                MarketData(order.symbol, datetime.now(UTC), float(price)),
                "signal_sell",
                quantity=close_qty,
            )
            if close_qty < quantity:
                quantity -= close_qty
                fee = Decimal(str(execution.fee)) * (quantity / (close_qty + quantity))
            else:
                return

        if not self._fits_free_margin(quantity * price):
            order.status = PaperOrderStatus.rejected
            self._log("order_rejected", "exceeds free margin (leverage cap)")
            return
        self.account.cash_balance += quantity * price - fee
        stop_loss = None
        take_profit = None
        signal_metadata = order.signal if isinstance(order.signal, dict) else {}
        atr_str = signal_metadata.get("metadata", {}).get("atr") if isinstance(signal_metadata.get("metadata"), dict) else signal_metadata.get("atr")
        if atr_str is not None:
            try:
                atr_value = Decimal(str(atr_str))
                stop_mult, tp_rr = self._stop_tp_params()
                stop_loss = price + atr_value * stop_mult
                risk_per_unit = stop_loss - price
                take_profit = price - risk_per_unit * tp_rr
            except Exception:
                pass
        if stop_loss is None:
            stop_loss = price * Decimal("1.15")
        if take_profit is None:
            take_profit = price * Decimal("0.85")
        leverage = self.exec.leverage if self.exec.market == "futures" else Decimal("1")
        margin = (quantity * price) / leverage if leverage > 0 else (quantity * price)
        liq_price = self.compute_liquidation_price_for(price, quantity, leverage, PaperPositionSide.short)
        existing = (
            self.db.query(PaperPosition)
            .filter(
                PaperPosition.account_id == self.account.id,
                PaperPosition.symbol == order.symbol,
                PaperPosition.is_open.is_(True),
                PaperPosition.side == "sell",
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
            existing.margin = (existing.margin or Decimal("0")) + margin
            existing.leverage = leverage
            existing.liquidation_price = self.compute_liquidation_price(existing)
        else:
            self.db.add(
                PaperPosition(
                    account_id=self.account.id,
                    symbol=order.symbol,
                    side="sell",
                    quantity=quantity,
                    average_entry_price=price,
                    last_price=price,
                    mark_price=price,
                    stop_loss=stop_loss,
                    initial_stop_loss=stop_loss,
                    take_profit=take_profit,
                    trailing_stop=stop_loss,
                    highest_price=None,
                    breakeven_triggered=False,
                    leverage=leverage,
                    margin=margin,
                    liquidation_price=liq_price,
                    position_side=PaperPositionSide.short if mode == PaperPositionMode.hedge else None,
                    last_funding_ts=datetime.now(UTC) if self.exec.funding_enabled else None,
                )
            )

    # ───────────────────────────── helpers ───────────────────────────────

    def close_position_sync(self, position: PaperPosition, data: MarketData, reason: str, quantity: Decimal | None = None) -> None:
        """Sync close wrapper used by reduce-only paths inside _apply_* (async
        ``close_position`` cannot be awaited mid-call from a sync helper). Delegates
        to a sync core that mirrors the async ``close_position``."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context already — do the work sync inline.
                self._close_position_core(position, data, reason, quantity)
                return
        except RuntimeError:
            pass
        self._close_position_core(position, data, reason, quantity)

    def _close_position_core(self, position: PaperPosition, data: MarketData, reason: str, quantity: Decimal | None = None) -> None:
        now = datetime.now(UTC)
        close_qty = quantity if quantity is not None and quantity < position.quantity else position.quantity
        is_short = position.side == "sell"
        close_side = OrderSide.buy if is_short else OrderSide.sell
        exit_sim_side = PaperSide.buy if is_short else PaperSide.sell
        execution = self.simulator.execute_market(
            order_id=0, side=exit_sim_side, quantity=float(close_qty), data=data, time_in_force="IOC",
        )
        exit_price = Decimal(str(execution.average_price))
        if is_short:
            pnl = (position.average_entry_price - exit_price) * close_qty - Decimal(str(execution.fee))
        else:
            pnl = (exit_price - position.average_entry_price) * close_qty - Decimal(str(execution.fee))
        pnl -= self._funding_cost(position, close_qty, now)
        entry_notional = position.average_entry_price * close_qty
        if is_short:
            self.account.cash_balance += pnl - entry_notional
        else:
            self.account.cash_balance += pnl + entry_notional
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
                symbol=position.symbol,
                side=close_side,
                price=exit_price,
                quantity=close_qty,
                fee=Decimal(str(execution.fee)),
                realized_pnl=pnl,
                exit_reason=reason,
            )
        )
        self._log("trade_closed", f"{position.symbol} partial closed (sync): {reason}", {"pnl": str(pnl)})

    def _round_quantity(self, quantity: Decimal) -> Decimal:
        from app.core.config import get_settings

        step = get_settings().paper_qty_step_default
        if step <= 0:
            return quantity
        from decimal import ROUND_DOWN

        return (quantity / Decimal(str(step))).quantize(Decimal("1"), rounding=ROUND_DOWN) * Decimal(str(step))

    def compute_liquidation_price_for(
        self, entry: Decimal, qty: Decimal, leverage: Decimal, side: PaperPositionSide
    ) -> Decimal | None:
        from app.core.config import get_settings

        if leverage is None or leverage <= 1:
            return None
        initial_margin = (entry * qty) / leverage
        if initial_margin <= 0:
            return None
        maint = Decimal(str(get_settings().paper_maintenance_margin_pct))
        loss_at_liq = initial_margin * (Decimal("1") - maint)
        per_unit_loss = loss_at_liq / qty if qty > 0 else Decimal("0")
        if side == PaperPositionSide.short:
            return entry + per_unit_loss
        return entry - per_unit_loss

    def _create_rejected_order(
        self, symbol: str, side: PaperSide, quantity: Decimal, order_type: PaperOrderType, reason: str,
        signal: dict | None, price: Decimal | None, stop_price: Decimal | None,
    ) -> PaperOrder:
        order = PaperOrder(
            account_id=self.account.id, symbol=symbol, side=OrderSide(side.value),
            order_type=order_type, status=PaperOrderStatus.rejected,
            requested_quantity=quantity, filled_quantity=Decimal("0"),
            limit_price=price, stop_price=stop_price,
            signal={"reason": reason, **(signal or {})},
        )
        self._log("order_rejected", f"{symbol}: {reason}")
        return order

    async def _record_execution_quality(
        self, order: PaperOrder, execution: PaperExecution, signal_time: datetime, submission_time: datetime
    ) -> None:
        try:
            from app.execution_quality.engine import ExecutionQualityEngine

            eq_engine = ExecutionQualityEngine(self.db)
            exec_order = eq_engine.record_order(
                strategy_name=order.signal.get("strategy", "manual") if isinstance(order.signal, dict) else "manual",
                symbol=order.symbol,
                side=order.side.value if hasattr(order.side, "value") else str(order.side),
                expected_price=Decimal(str(order.limit_price or order.average_fill_price or 0)),
                expected_quantity=order.requested_quantity,
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
                ack_time=ack_time,
            )
        except Exception:
            logger.warning("Paper execution-quality recording failed", exc_info=True)

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