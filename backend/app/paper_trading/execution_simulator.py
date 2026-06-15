import random

from app.paper_trading.models import MarketData, PaperExecution, PaperSide


class ExecutionSimulator:
    """Microstructure-aware fill simulator.

    Market orders ALWAYS pay at least the half-spread (a market buy lifts the
    ask, a market sell hits the bid) plus a size-dependent, strictly non-negative
    market-impact term. Slippage is one-sided and adverse by construction — a
    paper fill can never be better than the mid — so simulated PnL is not
    optimistically biased relative to live trading.
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

    def execute_market(self, order_id: int, side: PaperSide, quantity: float, data: MarketData) -> PaperExecution:
        is_buy = side == PaperSide.buy
        mid = data.price
        filled_qty = self._fillable(quantity, data)
        # One-sided adverse cost: half-spread + convex impact + adverse vol noise.
        half_spread = self._half_spread(data)
        impact = self._impact(filled_qty, data)
        vol_noise = abs(self.random.uniform(0.0, 0.0005)) * self._volatility_factor(data)
        adverse = half_spread + impact + vol_noise
        fill_price = mid * (1 + adverse) if is_buy else mid * (1 - adverse)
        fee = filled_qty * fill_price * self.taker_fee
        return PaperExecution(
            order_id=order_id,
            symbol=data.symbol,
            side=side,
            requested_quantity=quantity,
            filled_quantity=filled_qty,
            average_price=fill_price,
            fee=fee,
            latency_ms=self.random.randint(self.min_latency_ms, self.max_latency_ms),
            partial=filled_qty < quantity * 0.999,
        )

    def execute_limit(
        self, order_id: int, side: PaperSide, quantity: float, limit_price: float, data: MarketData
    ) -> PaperExecution | None:
        # A resting limit only fills when the market actually TRADES THROUGH it,
        # not merely touches it. Use the bar low/high when available (strict
        # trade-through), falling back to the last price.
        if side == PaperSide.buy:
            ref = data.low if data.low is not None else data.price
            can_fill = ref < limit_price
        else:
            ref = data.high if data.high is not None else data.price
            can_fill = ref > limit_price
        if not can_fill:
            return None
        # Queue/liquidity risk: even when crossed, only a fraction may fill.
        fill_ratio = min(1.0, max(0.25, self._light_book_depth(data) / max(quantity * limit_price, 1)))
        filled = quantity * fill_ratio
        fee = filled * limit_price * self.maker_fee
        return PaperExecution(
            order_id=order_id,
            symbol=data.symbol,
            side=side,
            requested_quantity=quantity,
            filled_quantity=filled,
            average_price=limit_price,
            fee=fee,
            latency_ms=self.random.randint(self.min_latency_ms, self.max_latency_ms),
            partial=fill_ratio < 0.999,
        )

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

    def _light_book_depth(self, data: MarketData) -> float:
        return max(data.volume * data.price * 0.08, 5_000)
