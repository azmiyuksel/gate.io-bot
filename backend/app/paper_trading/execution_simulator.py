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
        volatility_factor = self._volatility_factor(data)
        slippage = self.random.uniform(0.0001, 0.001) * volatility_factor
        fill_price = data.price * (1 + slippage if side == PaperSide.buy else 1 - slippage)
        fill_ratio = self.random.uniform(0.6, 1.0) if quantity * data.price > self._light_book_depth(data) else 1.0
        filled = quantity * fill_ratio
        fee = filled * fill_price * self.taker_fee
        return PaperExecution(
            order_id=order_id,
            symbol=data.symbol,
            side=side,
            requested_quantity=quantity,
            filled_quantity=filled,
            average_price=fill_price,
            fee=fee,
            latency_ms=self.random.randint(self.min_latency_ms, self.max_latency_ms),
            partial=fill_ratio < 0.999,
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
        return max(data.volume * data.price * 0.05, 1_000)
