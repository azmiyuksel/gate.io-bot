"""Adapts the CapitalPreservationStrategy to the paper-trading BaseStrategy interface.

Evaluates entries using real OHLC candles fetched via Gate.io REST API,
mirroring the live engine's evaluation path for meaningful signals.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from app.core.config import get_settings
from app.paper_trading.models import BaseStrategy, MarketData, PaperSide, TradingSignal
from app.services.strategy.signals import CapitalPreservationStrategy

logger = logging.getLogger(__name__)


class CapitalPreservationAdapter(BaseStrategy):
    """Wraps the live CapitalPreservationStrategy for use inside PaperTradingEngine."""

    def __init__(self, candle_window: int = 60, min_candles: int = 210) -> None:
        self._strategy = CapitalPreservationStrategy()
        # Paper runs deliberately looser entry thresholds than live (which stays
        # strict for capital preservation), so the simulation produces enough
        # activity to observe. Live thresholds are untouched.
        settings = get_settings()
        self._strategy.trend_filter_enabled = settings.paper_trend_filter_enabled
        self._strategy.rsi_threshold = Decimal(str(settings.paper_rsi_threshold))
        self._strategy.ema20_distance_pct = Decimal(str(settings.paper_ema20_distance_pct))
        self._last_signal: TradingSignal | None = None
        self._current_data: MarketData | None = None
        self._last_reason: str = ""
        self._candle_counts: dict[str, int] = {}
        self._last_atr: float | None = None

    def on_market_data(self, data: MarketData) -> None:
        self._current_data = data
        self._last_signal = None

    def generate_signal(self) -> TradingSignal | None:
        return self._last_signal

    def evaluate_real_candles(self, symbol: str, candles: list[dict]) -> TradingSignal | None:
        """Evaluate the strategy on real OHLC candles (preferred path).

        Mirrors the live engine: feed genuine candles to the strategy rather than
        tick-aggregated synthetic bars, so EMA200/RSI/ATR are meaningful.
        """
        signal = self._strategy.evaluate(candles)
        self._last_reason = signal.reason
        if signal.diagnostics:
            self._last_reason = f"{signal.reason} (RSI={signal.diagnostics.get('rsi', '?')})"
        self._candle_counts[symbol] = len(candles)
        self._last_atr = float(signal.atr_value) if signal.atr_value else None
        if not signal.should_enter:
            return None
        direction = signal.direction
        side = PaperSide.sell if direction == "short" else PaperSide.buy
        logger.info("[%s] candles=%d signal=%s reason=%s", symbol, len(candles), direction.upper(), signal.reason)
        return TradingSignal(
            symbol=symbol,
            side=side,
            strength=0.8,
            strategy=self._strategy.name,
            timestamp=datetime.now(UTC),
            metadata={
                "reason": signal.reason,
                "atr": str(signal.atr_value),
                "entry": str(signal.entry_price),
                "direction": direction,
            },
        )

    @property
    def last_reason(self) -> str:
        return self._last_reason

    @property
    def candle_counts(self) -> dict[str, int]:
        return dict(self._candle_counts)

    def position_size(self, equity: float, price: float) -> float:
        """ATR/risk-based sizing: size so the loss-to-stop equals
        ``paper_position_risk_pct`` of equity, scaled by the ATR stop distance,
        capped at ``paper_max_capital_per_trade_pct`` of equity. Falls back to a
        conservative fixed-notional fraction when ATR is unavailable."""
        if price <= 0:
            return 0.0
        settings = get_settings()
        notional_cap = equity * settings.paper_max_capital_per_trade_pct / price
        if self._last_atr and self._last_atr > 0:
            stop_distance = settings.paper_atr_stop_multiplier * self._last_atr
            if stop_distance > 0:
                risk_budget = equity * settings.paper_position_risk_pct
                return min(risk_budget / stop_distance, notional_cap)
        return min(equity * settings.paper_fallback_capital_pct / price, notional_cap)
