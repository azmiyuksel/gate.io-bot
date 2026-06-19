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
from app.services.strategy.momentum_breakout import (
    STRATEGY_NAME as MOMENTUM_NAME,
    MomentumBreakoutStrategy,
)
from app.services.strategy.signals import (
    STRATEGY_NAME as CAPITAL_PRESERVATION_NAME,
    CapitalPreservationStrategy,
)

logger = logging.getLogger(__name__)

_KNOWN_PAPER_STRATEGIES = (MOMENTUM_NAME, CAPITAL_PRESERVATION_NAME)


def _build_strategy_by_name(name, settings):
    """Instantiate a paper strategy BY NAME (used for regime routing too).

    The capital-preservation strategy runs with the deliberately looser paper
    thresholds it was tuned for. Hard-fails on an unknown name, matching the live
    factory — a typo silently running the wrong strategy is worse than a startup
    error (paper would trade an unvalidated strategy under a mistyped name,
    diverging from live).
    """
    if name == CAPITAL_PRESERVATION_NAME:
        strat = CapitalPreservationStrategy()
        strat.trend_filter_enabled = settings.paper_trend_filter_enabled
        strat.rsi_threshold = Decimal(str(settings.paper_rsi_threshold))
        strat.ema20_distance_pct = Decimal(str(settings.paper_ema20_distance_pct))
        strat.trend_tolerance_pct = Decimal(str(settings.paper_trend_tolerance_pct))
        return strat
    if name == MOMENTUM_NAME:
        return MomentumBreakoutStrategy()
    raise ValueError(
        f"Unknown PAPER_STRATEGY '{name}'. "
        f"Known strategies: {list(_KNOWN_PAPER_STRATEGIES)}. "
        f"Check .env for a typo."
    )


def _build_strategy(settings):
    """Instantiate the configured paper strategy (default momentum/breakout)."""
    return _build_strategy_by_name(settings.paper_strategy, settings)


class CapitalPreservationAdapter(BaseStrategy):
    """Adapts the configured paper strategy to the PaperTradingEngine interface.

    Named for history; the active strategy is selected via ``paper_strategy``
    (default ``momentum_breakout_v1``).
    """

    def __init__(self, candle_window: int = 60, min_candles: int = 210) -> None:
        settings = get_settings()
        self._strategy = _build_strategy(settings)
        # Cache of underlying strategies by name for regime routing (built lazily).
        self._strategy_cache: dict = {self._strategy.name: self._strategy}
        self._last_signal: TradingSignal | None = None
        self._current_data: MarketData | None = None
        self._last_reason: str = ""
        self._last_reason_code: str = ""
        self._candle_counts: dict[str, int] = {}
        self._last_atr: float | None = None

    def route_for_regime(self, regime_type) -> str:
        """Swap the active underlying strategy to the one routed for the given
        market regime (momentum in trends/breakouts, mean-reversion in ranges).
        Returns the active strategy name. Used only when REGIME_ROUTING_ENABLED."""
        from app.services.strategy.router import route_strategy_name

        settings = get_settings()
        name = route_strategy_name(regime_type, settings.paper_strategy)
        strat = self._strategy_cache.get(name)
        if strat is None:
            strat = _build_strategy_by_name(name, settings)
            self._strategy_cache[name] = strat
        self._strategy = strat
        return name

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
        # `last_reason` is a human-readable string (with the live RSI) for log
        # messages; `last_reason_code` is the STABLE reason code used for grouping.
        # Keeping the RSI out of the code is essential — otherwise every evaluation
        # produces a unique reason and the diagnostics tally grows without bound.
        self._last_reason_code = signal.reason
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
    def last_reason_code(self) -> str:
        """Stable reason code (no embedded RSI) for diagnostics aggregation."""
        return self._last_reason_code

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
