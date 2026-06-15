import random

from app.paper_trading.models import MarketData, PaperExecution, PaperSide


class ExecutionSimulator:
    def __init__(
        self,
        maker_fee: float = 0.001,
        taker_fee: float = 0.001,
        min_latency_ms: int = 100,
        max_latency_ms: int = 1000,
        seed: int | None = None,
    ) -> None:
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.min_latency_ms = min_latency_ms
        self.max_latency_ms = max_latency_ms
        self.random = random.Random(seed)

    def execute_market(self, order_id: int, side: PaperSide, quantity: float, data: MarketData) -> PaperExecution:
        volatility_factor = max(self._volatility_factor(data), 1.0)
        filled, avg_price = self._tiered_fill(quantity, data)
        extra_slip = abs(self.random.uniform(-0.001, 0.001)) * volatility_factor
        fill_price = avg_price * (1 + extra_slip if side == PaperSide.buy else 1 - extra_slip)
        filled_qty = min(filled, quantity)
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
        can_fill = data.price <= limit_price if side == PaperSide.buy else data.price >= limit_price
        if not can_fill:
            return None
        fill_ratio = min(1.0, max(0.25, self._light_book_depth(data) / max(quantity * data.price, 1)))
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

    def _volatility_factor(self, data: MarketData) -> float:
        if data.high is None or data.low is None or data.price <= 0:
            return 1.0
        intrabar_range = abs(data.high - data.low) / data.price
        return min(4.0, 1.0 + intrabar_range * 20)

    def _light_book_depth(self, data: MarketData) -> float:
        return max(data.volume * data.price * 0.08, 5_000)

    def _tiered_fill(self, quantity: float, data: MarketData) -> tuple[float, float]:
        if quantity <= 0:
            return 0.0, data.price
        l1_depth = max(data.volume * data.price * 0.03, 2_000)
        l2_depth = max(data.volume * data.price * 0.05, 5_000)
        vol_factor = self._volatility_factor(data)
        base_slip = self.random.uniform(-0.001, 0.001) * vol_factor
        filled = 0.0
        total_cost = 0.0
        remaining = quantity * data.price
        if remaining <= l1_depth:
            filled = quantity
            total_cost = filled * data.price * (1 + base_slip)
            return filled, total_cost / filled if filled else data.price
        filled += l1_depth / data.price
        total_cost += l1_depth * (1 + base_slip)
        remaining = quantity * data.price - l1_depth
        if remaining <= l2_depth:
            l2_slip_mult = 1.5
            l2_price = data.price * (1 + base_slip * l2_slip_mult)
            filled += remaining / l2_price
            total_cost += remaining
            return filled, total_cost / filled if filled else data.price
        filled += l2_depth / data.price
        total_cost += l2_depth * (1 + base_slip * 1.5)
        remaining = quantity * data.price - l1_depth - l2_depth
        wide_slip_mult = 2.5
        wide_price = data.price * (1 + base_slip * wide_slip_mult)
        filled += remaining / wide_price
        total_cost += remaining
        return filled, total_cost / filled if filled else data.price
