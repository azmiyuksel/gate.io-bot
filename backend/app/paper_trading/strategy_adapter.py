"""Adapts the CapitalPreservationStrategy to the paper-trading BaseStrategy interface.

Collects incoming tick-level MarketData, aggregates into candle-like records,
and evaluates the strategy when enough history is available.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import UTC, datetime

from app.paper_trading.models import BaseStrategy, MarketData, PaperSide, TradingSignal
from app.services.strategy.signals import CapitalPreservationStrategy

logger = logging.getLogger(__name__)


class CapitalPreservationAdapter(BaseStrategy):
    """Wraps the live CapitalPreservationStrategy for use inside PaperTradingEngine."""

    def __init__(self, candle_window: int = 60, min_candles: int = 210) -> None:
        self._strategy = CapitalPreservationStrategy()
        # EMA200 trend filter enabled: only enter long positions above the 200 EMA
        # to avoid buying in confirmed downtrends (capital preservation).
        self._strategy.trend_filter_enabled = True
        self._candle_window = candle_window  # ticks per synthetic candle
        self._min_candles = min_candles  # strategy needs >= 210
        self._tick_buffers: dict[str, list[MarketData]] = defaultdict(list)
        self._candles: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=500))
        self._last_signal: TradingSignal | None = None
        self._current_data: MarketData | None = None
        self._last_reason: str = ""
        self._candle_counts: dict[str, int] = {}

    def on_market_data(self, data: MarketData) -> None:
        self._current_data = data
        self._last_signal = None
        buf = self._tick_buffers[data.symbol]
        buf.append(data)
        if len(buf) >= self._candle_window:
            self._aggregate_candle(data.symbol, buf)
            self._tick_buffers[data.symbol] = []
            self._evaluate(data.symbol)

    def generate_signal(self) -> TradingSignal | None:
        return self._last_signal

    def evaluate_real_candles(self, symbol: str, candles: list[dict]) -> TradingSignal | None:
        """Evaluate the strategy on real OHLC candles (preferred path).

        Mirrors the live engine: feed genuine candles to the strategy rather than
        tick-aggregated synthetic bars, so EMA200/RSI/ATR are meaningful.
        """
        signal = self._strategy.evaluate(candles)
        self._last_reason = signal.reason
        self._candle_counts[symbol] = len(candles)
        if not signal.should_buy:
            return None
        logger.info("[%s] candles=%d signal=BUY reason=%s", symbol, len(candles), signal.reason)
        return TradingSignal(
            symbol=symbol,
            side=PaperSide.buy,
            strength=0.8,
            strategy=self._strategy.name,
            timestamp=datetime.now(UTC),
            metadata={
                "reason": signal.reason,
                "atr": str(signal.atr_value),
                "entry": str(signal.entry_price),
            },
        )

    def prewarm_candles(self, symbol: str, candles: list[dict]) -> None:
        converted = []
        for c in candles:
            converted.append({
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c.get("volume", 0)),
            })
        self._candles[symbol] = deque(converted, maxlen=500)
        self._candle_counts[symbol] = len(converted)
        # Trigger immediate evaluation if we have enough candles
        self._evaluate(symbol)

    @property
    def last_reason(self) -> str:
        return self._last_reason

    @property
    def candle_counts(self) -> dict[str, int]:
        return dict(self._candle_counts)

    def position_size(self, equity: float, price: float) -> float:
        if price <= 0:
            return 0.0
        return equity * 0.02 / price

    def _aggregate_candle(self, symbol: str, ticks: list[MarketData]) -> None:
        prices = [t.price for t in ticks]
        volumes = [t.volume for t in ticks]
        candle = {
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": sum(volumes),
        }
        self._candles[symbol].append(candle)

    def _evaluate(self, symbol: str) -> None:
        candles = list(self._candles[symbol])
        self._candle_counts[symbol] = len(candles)
        if len(candles) < self._min_candles:
            if len(candles) % 50 == 0:
                logger.info("[%s] warming up: %d/%d candles", symbol, len(candles), self._min_candles)
            return
        signal = self._strategy.evaluate(candles)
        if signal.should_buy:
            if self._current_data is not None:
                self._last_signal = TradingSignal(
                    symbol=symbol,
                    side=PaperSide.buy,
                    strength=0.8,
                    strategy="capital_preservation_v1",
                    timestamp=self._current_data.timestamp if self._current_data else datetime.now(UTC),
                    metadata={"reason": signal.reason, "atr": str(signal.atr_value)},
                )
            self._last_reason = signal.reason
            logger.info("[%s] candles=%d signal=BUY reason=%s", symbol, len(candles), signal.reason)
        else:
            self._last_reason = signal.reason
            if len(candles) == self._min_candles:
                logger.info("[%s] candles=%d signal=NO reason=%s", symbol, len(candles), signal.reason)
