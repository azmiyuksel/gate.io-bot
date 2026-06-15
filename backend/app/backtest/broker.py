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
        maker_fee_rate: float | None = None,
        funding_daily_rate: float = 0.0,
    ) -> None:
        self.portfolio = portfolio
        # Financing carry (perp funding / spot borrow) per day of holding.
        self.funding_daily_rate = funding_daily_rate
        # Taker fee applies to market orders and stop-loss exits that cross the
        # spread; maker fee applies to resting limit entries and take-profit exits.
        self.commission_rate = commission_rate
        self.taker_fee_rate = commission_rate
        self.maker_fee_rate = maker_fee_rate if maker_fee_rate is not None else commission_rate
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
        return self._open(candle, symbol, quantity, fill_price, stop_loss, take_profit, self.taker_fee_rate)

    def limit_buy(
        self,
        candle: pd.Series,
        symbol: str,
        quantity: float,
        limit_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> BacktestPosition | None:
        """Maker entry: fills only if this bar trades down to the limit price.

        Models a resting post-only buy — you save the taker fee and spread/slippage
        but miss the trade entirely when price never comes back to your limit.
        """
        if float(candle["low"]) > limit_price:
            return None  # not filled this bar -> signal missed
        return self._open(candle, symbol, quantity, limit_price, stop_loss, take_profit, self.maker_fee_rate)

    def _open(
        self,
        candle: pd.Series,
        symbol: str,
        quantity: float,
        fill_price: float,
        stop_loss: float,
        take_profit: float,
        fee_rate: float,
    ) -> BacktestPosition | None:
        gross_cost = fill_price * quantity
        fee = gross_cost * fee_rate
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
            breakeven_triggered=False,
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

    def manage_exits(self, candle: pd.Series, trailing_stop_pct: float = 0.01,
                     breakeven_trigger_pct: float = 0.02) -> None:
        high = float(candle["high"])
        low = float(candle["low"])
        for position in list(self.portfolio.positions):
            position.highest_price = max(position.highest_price, high)
            trailing_stop = position.highest_price * (1 - trailing_stop_pct)
            if trailing_stop > position.stop_loss:
                position.stop_loss = trailing_stop
            # Breakeven stop: move SL to entry when profit exceeds threshold
            if not position.breakeven_triggered and breakeven_trigger_pct > 0:
                profit_pct = (position.highest_price - position.entry_price) / position.entry_price
                if profit_pct >= breakeven_trigger_pct and position.stop_loss < position.entry_price:
                    position.stop_loss = position.entry_price
                    position.breakeven_triggered = True
            if low <= position.stop_loss:
                # Stop-loss is a market (taker) exit that crosses the spread.
                self._close(position, candle, position.stop_loss, "stop_loss", maker=False)
            elif high >= position.take_profit:
                # Take-profit is a resting limit (maker) exit — no spread/slippage.
                self._close(position, candle, position.take_profit, "take_profit", maker=True)

    def _close(
        self,
        position: BacktestPosition,
        candle: pd.Series,
        price: float,
        reason: str,
        maker: bool = False,
    ) -> None:
        if maker:
            fill_price = price  # resting limit fills at the target, no slippage
            fee_rate = self.maker_fee_rate
        else:
            fill_price = self._sell_fill_price(price)  # market exit crosses the spread
            fee_rate = self.taker_fee_rate
        fee = fill_price * position.quantity * fee_rate
        # Charge financing carry for the holding period so multi-day holds are not
        # cost-free — funding/borrow is a first-order cost for any real position.
        fee += self._funding_cost(position, candle.name)
        self.portfolio.close_position(position, candle.name, fill_price, fee, reason)

    def _funding_cost(self, position: BacktestPosition, exit_time) -> float:
        if self.funding_daily_rate <= 0:
            return 0.0
        try:
            held_days = (exit_time - position.entry_time).total_seconds() / 86_400.0
        except (TypeError, AttributeError):
            return 0.0
        if held_days <= 0:
            return 0.0
        return position.entry_price * position.quantity * self.funding_daily_rate * held_days

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
        matching = [p for p in self.portfolio.positions if p.symbol == order.symbol]
        if matching:
            reference = order.limit_price or order.stop_price or float(candle["open"])
            self._close(matching[0], candle, reference, f"{order.order_type}_sell")

    def _buy_fill_price(self, price: float) -> float:
        return price * (1 + self.spread_rate / 2 + self.slippage_rate)

    def _sell_fill_price(self, price: float) -> float:
        return price * (1 - self.spread_rate / 2 - self.slippage_rate)
