import pandas as pd

from app.backtest.models import BacktestPosition, OrderSide, OrderType, SimulatedOrder
from app.backtest.portfolio import Portfolio


class VirtualBroker:
    def __init__(
        self,
        portfolio: Portfolio,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.0005,
        spread_rate: float = 0.0002,
        order_latency_candles: int = 1,
    ) -> None:
        self.portfolio = portfolio
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.spread_rate = spread_rate
        self.order_latency_candles = order_latency_candles
        self.pending_orders: list[SimulatedOrder] = []

    def submit_order(self, order: SimulatedOrder) -> None:
        order.latency_remaining = self.order_latency_candles
        self.pending_orders.append(order)

    def market_buy(
        self, candle: pd.Series, symbol: str, quantity: float, stop_loss: float, take_profit: float
    ) -> BacktestPosition | None:
        fill_price = self._buy_fill_price(float(candle["open"]))
        gross_cost = fill_price * quantity
        fee = gross_cost * self.commission_rate
        if self.portfolio.cash < gross_cost + fee:
            return None
        position = BacktestPosition(
            symbol=symbol,
            entry_time=candle.name,
            entry_price=fill_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            fee_paid=fee,
            highest_price=fill_price,
        )
        self.portfolio.open_position(position, gross_cost)
        return position

    def process_orders(self, candle: pd.Series) -> None:
        executable: list[SimulatedOrder] = []
        for order in self.pending_orders:
            if order.latency_remaining > 0:
                order.latency_remaining -= 1
                continue
            if self._is_triggered(order, candle):
                executable.append(order)
        for order in executable:
            self._execute_order(order, candle)
            self.pending_orders.remove(order)

    def manage_exits(self, candle: pd.Series, trailing_stop_pct: float = 0.01) -> None:
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        for position in list(self.portfolio.positions):
            position.highest_price = max(position.highest_price, high)
            trailing_stop = position.highest_price * (1 - trailing_stop_pct)
            if trailing_stop > position.stop_loss:
                position.stop_loss = trailing_stop
            if low <= position.stop_loss:
                self._close(position, candle, position.stop_loss, "stop_loss")
            elif high >= position.take_profit:
                self._close(position, candle, position.take_profit, "take_profit")

    def _close(self, position: BacktestPosition, candle: pd.Series, price: float, reason: str) -> None:
        fill_price = self._sell_fill_price(price)
        fee = fill_price * position.quantity * self.commission_rate
        self.portfolio.close_position(position, candle.name, fill_price, fee, reason)

    def _is_triggered(self, order: SimulatedOrder, candle: pd.Series) -> bool:
        high = float(candle["high"])
        low = float(candle["low"])
        if order.order_type == OrderType.market:
            return True
        if order.order_type == OrderType.limit and order.limit_price is not None:
            return low <= order.limit_price if order.side == OrderSide.buy else high >= order.limit_price
        if order.order_type == OrderType.stop and order.stop_price is not None:
            return high >= order.stop_price if order.side == OrderSide.buy else low <= order.stop_price
        if order.order_type == OrderType.stop_limit and order.stop_price and order.limit_price:
            stop_hit = high >= order.stop_price if order.side == OrderSide.buy else low <= order.stop_price
            limit_hit = low <= order.limit_price if order.side == OrderSide.buy else high >= order.limit_price
            return stop_hit and limit_hit
        return False

    def _execute_order(self, order: SimulatedOrder, candle: pd.Series) -> None:
        if order.side == OrderSide.buy:
            reference = order.limit_price or order.stop_price or float(candle["open"])
            fill_price = self._buy_fill_price(reference)
            stop_loss = order.attached_stop_loss or fill_price * 0.98
            take_profit = order.attached_take_profit or fill_price * 1.04
            self.market_buy(candle, order.symbol, order.quantity, stop_loss, take_profit)
            return
        if self.portfolio.positions:
            reference = order.limit_price or order.stop_price or float(candle["open"])
            self._close(self.portfolio.positions[0], candle, reference, f"{order.order_type}_sell")

    def _buy_fill_price(self, price: float) -> float:
        return price * (1 + self.spread_rate / 2 + self.slippage_rate)

    def _sell_fill_price(self, price: float) -> float:
        return price * (1 - self.spread_rate / 2 - self.slippage_rate)
