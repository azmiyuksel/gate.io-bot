from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class PaperSide(StrEnum):
    buy = "buy"
    sell = "sell"


class PaperOrderType(StrEnum):
    market = "market"
    limit = "limit"
    stop_loss = "stop_loss"
    stop_limit = "stop_limit"


@dataclass(frozen=True)
class MarketData:
    symbol: str
    timestamp: datetime
    price: float
    volume: float = 0
    bid: float | None = None
    ask: float | None = None
    high: float | None = None
    low: float | None = None
    source: str = "gateio"


@dataclass(frozen=True)
class TradingSignal:
    symbol: str
    side: PaperSide
    strength: float
    strategy: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "strength": self.strength,
            "strategy": self.strategy,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class PaperExecution:
    order_id: int
    symbol: str
    side: PaperSide
    requested_quantity: float
    filled_quantity: float
    average_price: float
    fee: float
    latency_ms: int
    partial: bool
    reason: str = "filled"


class BaseStrategy:
    def on_market_data(self, data: MarketData) -> None:
        pass

    def generate_signal(self) -> TradingSignal | None:
        return None

    def evaluate_real_candles(self, symbol: str, candles: list[dict]) -> TradingSignal | None:
        """Evaluate entries on real OHLC candles. Returns a buy signal or None."""
        return None

    def position_size(self, equity: float, price: float) -> float:
        return 0
