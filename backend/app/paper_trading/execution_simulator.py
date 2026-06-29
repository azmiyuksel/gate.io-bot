import random

from app.paper_trading.models import MarketData, PaperExecution, PaperSide


class ExecutionSimulator:
    """Microstructure-aware fill simulator.

    Market orders ALWAYS pay at least the half-spread (a market buy lifts the
    ask, a market sell hits the bid) plus a size-dependent, strictly non-negative
    market-impact term. Slippage is one-sided and adverse by construction — a
    paper fill can never be better than the mid — so simulated PnL is not
    optimistically biased relative to live trading.

    Limit orders only fill when the bar TRADES THROUGH the limit (strict
    trade-through, not merely touches), pay the maker fee, and are subject to
    queue-depth partial fills. Post-only (``POST`` TIF) orders are rejected if
    they would cross the book (they must rest as maker). IOC/FOK semantics drop
    or cancel any unfilled remainder immediately rather than resting.

    Latency is now MODELLED, not merely recorded: the caller is expected to
    ``await asyncio.sleep(latency_ms/1000)`` between submit and fill, and the
    fill price reflects a small random-walk drift over that window so simulated
    fills move against the trader as they would live — instead of using the same
    ``data.price`` the signal was generated against.
    """

    def __init__(
        self,
        maker_fee: float = 0.0002,
        taker_fee: float = 0.001,
        min_latency_ms: int = 100,
        max_latency_ms: int = 1000,
        seed: int | None = None,
        default_half_spread: float = 0.0001,
        impact_coef: float = 0.001,
        depth_fraction: float = 0.05,
        min_depth: float = 5_000.0,
        max_impact: float = 0.02,
        max_fill_fraction: float = 0.10,
    ) -> None:
        # Maker (2 bps) is cheaper than taker (10 bps), which is the whole
        # economic reason to post liquidity. Taker stays conservative so paper
        # PnL is not overstated relative to live. Overridable per VIP tier.
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.min_latency_ms = min_latency_ms
        self.max_latency_ms = max_latency_ms
        self.random = random.Random(seed)
        self.default_half_spread = default_half_spread
        self.impact_coef = impact_coef
        self.depth_fraction = depth_fraction
        self.min_depth = min_depth
        self.max_impact = max_impact
        self.max_fill_fraction = max_fill_fraction

    def execute_market(
        self,
        order_id: int,
        side: PaperSide,
        quantity: float,
        data: MarketData,
        *,
        time_in_force: str = "GTC",
    ) -> PaperExecution:
        """Taker-market fill. TIF affects the partial-fill remainder policy:

        - GTC  : the filled portion is returned; leftover rests on the book.
                 (The broker records ``partially_filled`` and the engine re-evaluates
                 the resting residual on subsequent ticks.)
        - IOC  : same fill, but the caller will cancel the leftover immediately.
        - FOK  : cap-by-depth; if the whole quantity can't fill, NO fill.
        - POST : a market order can never be post-only, but the broker routes
                 POST orders through the limit path — this branch is unreachable.
        """
        is_buy = side == PaperSide.buy
        mid = data.price
        # FOK: must be wholly fillable or reject entirely.
        if time_in_force == "FOK":
            capacity_notional = max(data.volume * data.price * self.max_fill_fraction, self.min_depth)
            if quantity * data.price > capacity_notional:
                return PaperExecution(
                    order_id=order_id, symbol=data.symbol, side=side,
                    requested_quantity=quantity, filled_quantity=0.0,
                    average_price=mid, fee=0.0, latency_ms=0, partial=False,
                    reason="fok_not_fillable",
                )
            filled_qty = quantity
        else:
            filled_qty = self._fillable(quantity, data)
        # One-sided adverse cost: half-spread + convex impact + adverse vol noise
        # PLUS a latency-drift term so the price moved over the (now awaited)
        # execution window is reflected in the fill (was cosmetic before).
        half_spread = self._half_spread(data)
        impact = self._impact(filled_qty, data)
        vol_noise = abs(self.random.uniform(0.0, 0.0005)) * self._volatility_factor(data)
        latency_ms = self.random.randint(self.min_latency_ms, self.max_latency_ms)
        latency_drift = self._latency_drift(data, latency_ms)
        adverse = half_spread + impact + vol_noise + latency_drift
        fill_price = mid * (1 + adverse) if is_buy else mid * (1 - adverse)
        fee = filled_qty * fill_price * self.taker_fee
        partial = filled_qty < quantity * 0.999
        reason = "filled" if not partial else "partial_fill"
        if time_in_force == "IOC" and partial:
            reason = "ioc_partial"
        return PaperExecution(
            order_id=order_id,
            symbol=data.symbol,
            side=side,
            requested_quantity=quantity,
            filled_quantity=filled_qty,
            average_price=fill_price,
            fee=fee,
            latency_ms=latency_ms,
            partial=partial,
            reason=reason,
        )

    def execute_limit(
        self,
        order_id: int,
        side: PaperSide,
        quantity: float,
        limit_price: float,
        data: MarketData,
        *,
        time_in_force: str = "GTC",
        post_only: bool = False,
    ) -> PaperExecution | None:
        """Limit fill simulation.

        A resting limit only fills when the market TRADES THROUGH it (strict
        trade-through on the bar low/high). Post-only rejects if the order would
        cross the book (must rest as maker). Queue/liquidity partial applies.

        Returns ``None`` when the order must continue resting (GTC) — the caller
        keeps it pending. Returns a ``PaperExecution`` (possibly zero-fill with
        a reason) when the order cancels (IOC/FOK/POST cross).
        """
        is_buy = side == PaperSide.buy
        # POST-ONLY: a buy above the ask (or sell below the bid) would cross and
        # take liquidity — reject instead of resting.
        if post_only:
            if data.ask is not None and is_buy and limit_price >= data.ask:
                return PaperExecution(
                    order_id=order_id, symbol=data.symbol, side=side,
                    requested_quantity=quantity, filled_quantity=0.0,
                    average_price=limit_price, fee=0.0, latency_ms=0, partial=False,
                    reason="post_only_would_cross",
                )
            if data.bid is not None and not is_buy and limit_price <= data.bid:
                return PaperExecution(
                    order_id=order_id, symbol=data.symbol, side=side,
                    requested_quantity=quantity, filled_quantity=0.0,
                    average_price=limit_price, fee=0.0, latency_ms=0, partial=False,
                    reason="post_only_would_cross",
                )
        if is_buy:
            ref = data.low if data.low is not None else data.price
            can_fill = ref < limit_price
        else:
            ref = data.high if data.high is not None else data.price
            can_fill = ref > limit_price
        if not can_fill:
            # Did not trade through — order rests (GTC) or cancels (IOC/FOK).
            if time_in_force in ("IOC", "FOK"):
                return PaperExecution(
                    order_id=order_id, symbol=data.symbol, side=side,
                    requested_quantity=quantity, filled_quantity=0.0,
                    average_price=limit_price, fee=0.0, latency_ms=0, partial=False,
                    reason="ioc_not_crossed" if time_in_force == "IOC" else "fok_not_crossed",
                )
            return None
        # Queue/liquidity risk: even when crossed, only a fraction may fill.
        full_depth = max(self._light_book_depth(data), 1.0)
        fill_ratio = min(1.0, max(0.25, full_depth / max(quantity * limit_price, 1)))
        # FOK: require whole fill or nothing.
        if time_in_force == "FOK" and fill_ratio < 0.999:
            return PaperExecution(
                order_id=order_id, symbol=data.symbol, side=side,
                requested_quantity=quantity, filled_quantity=0.0,
                average_price=limit_price, fee=0.0, latency_ms=0, partial=False,
                reason="fok_queue_partial",
            )
        filled = quantity * fill_ratio
        fee = filled * limit_price * self.maker_fee
        partial = fill_ratio < 0.999
        reason = "filled" if not partial else "partial_fill"
        if time_in_force == "IOC" and partial:
            reason = "ioc_partial"
        return PaperExecution(
            order_id=order_id,
            symbol=data.symbol,
            side=side,
            requested_quantity=quantity,
            filled_quantity=filled,
            average_price=limit_price,
            fee=fee,
            latency_ms=self.random.randint(self.min_latency_ms, self.max_latency_ms),
            partial=partial,
            reason=reason,
        )

    def execute_stop(
        self,
        order_id: int,
        side: PaperSide,
        quantity: float,
        stop_price: float,
        data: MarketData,
    ) -> bool:
        """Trigger a stop-order when the bar breaches the stop price.

        Returns True when the stop triggers (the broker then routes a market /
        limit child order through ``execute_market`` / ``execute_limit``). For a
        buy stop: trigger when price >= stop_price. For a sell stop: when price
        <= stop_price.
        """
        if side == PaperSide.buy:
            return data.price >= stop_price
        return data.price <= stop_price

    def _half_spread(self, data: MarketData) -> float:
        """Half the bid/ask spread as a fraction of mid (>= 0). Falls back to a
        configured default when the book is not quoted."""
        if (
            data.bid is not None
            and data.ask is not None
            and data.bid > 0
            and data.ask > data.bid
            and data.price > 0
        ):
            return (data.ask - data.bid) / 2.0 / data.price
        return max(0.0, self.default_half_spread)

    def _impact(self, quantity: float, data: MarketData) -> float:
        """Strictly non-negative, convex (square-root) market impact as a function
        of order participation in available depth."""
        if quantity <= 0 or data.price <= 0:
            return 0.0
        notional = quantity * data.price
        depth = max(data.volume * data.price * self.depth_fraction, self.min_depth)
        if depth <= 0:
            return self.max_impact
        participation = notional / depth
        return min(self.max_impact, self.impact_coef * (participation ** 0.5))

    def _fillable(self, quantity: float, data: MarketData) -> float:
        """Cap the filled quantity by available bar liquidity (partial fills for
        oversized orders rather than infinite liquidity)."""
        if quantity <= 0 or data.price <= 0:
            return max(0.0, quantity)
        capacity_notional = max(data.volume * data.price * self.max_fill_fraction, self.min_depth)
        notional = quantity * data.price
        if notional <= capacity_notional:
            return quantity
        return capacity_notional / data.price

    def _volatility_factor(self, data: MarketData) -> float:
        if data.high is None or data.low is None or data.price <= 0:
            return 1.0
        intrabar_range = abs(data.high - data.low) / data.price
        return min(4.0, 1.0 + intrabar_range * 20)

    def _latency_drift(self, data: MarketData, latency_ms: int) -> float:
        """Adverse price drift over the (now awaited) latency window.

        A random walk of σ proportional to the latent volatility, scaled by the
        latency in seconds, expressed as a fraction of mid. Strictly
        non-negative — slippage only ever costs the taker, never helps.
        """
        if latency_ms <= 0:
            return 0.0
        sigma = self._volatility_factor(data) * 0.0002  # ~2bp per ~vol factor
        seconds = latency_ms / 1000.0
        # |N(0, sigma^2 * t)| — distance of a 1-D random walk at time t.
        return abs(self.random.gauss(0.0, sigma * (seconds ** 0.5)))

    def _light_book_depth(self, data: MarketData) -> float:
        return max(data.volume * data.price * 0.08, 5_000)