from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import pandas as pd


SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}
TIMEFRAME_TO_PANDAS = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}


class OrderType(StrEnum):
    market = "market"
    limit = "limit"
    stop = "stop"
    stop_limit = "stop_limit"


class OrderSide(StrEnum):
    buy = "buy"
    sell = "sell"


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    timeframe: str
    start_at: datetime
    end_at: datetime
    initial_cash: float = 10_000
    commission_rate: float = 0.001  # taker fee (market orders / stop-loss exits)
    maker_fee_rate: float = 0.0008  # maker fee (resting limit entries / take-profit exits)
    slippage_rate: float = 0.0005
    spread_rate: float = 0.0002
    order_latency_candles: int = 1
    # Entry execution: "market" (taker, always fills next open) or
    # "limit" (maker, fills next bar only if price trades down to the signal price).
    execution_mode: str = "market"
    # For limit entries, post the buy this fraction below the signal close.
    limit_offset: float = 0.0
    max_open_positions: int = 3
    max_capital_per_trade_pct: float = 0.01
    parameters: dict = field(default_factory=dict)


@dataclass
class SimulatedOrder:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    created_at: pd.Timestamp
    limit_price: float | None = None
    stop_price: float | None = None
    attached_stop_loss: float | None = None
    attached_take_profit: float | None = None
    latency_remaining: int = 0


@dataclass
class BacktestPosition:
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    fee_paid: float
    highest_price: float
    breakeven_triggered: bool = False


@dataclass
class BacktestTradeResult:
    symbol: str
    side: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: float
    fee: float
    pnl: float
    pnl_pct: float
    exit_reason: str
