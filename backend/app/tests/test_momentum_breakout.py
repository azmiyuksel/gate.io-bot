"""Tests for the frequent momentum/breakout strategy (long + short)."""
from decimal import Decimal

from app.services.strategy.momentum_breakout import MomentumBreakoutStrategy


def _candle(close: float, high: float | None = None, low: float | None = None, volume: float = 1000.0) -> dict:
    high = high if high is not None else close * 1.003
    low = low if low is not None else close * 0.997
    return {"open": close, "high": high, "low": low, "close": close, "volume": volume}


def _base_series(n: int, start: float, step: float) -> list[dict]:
    """A mild, choppy trend so EMAs align but RSI stays out of the extremes.

    Each bar drifts ``step`` in the trend direction, then gives back 60% of it,
    so net drift is one-directional while gains≈losses keep RSI mid-range.
    """
    candles = []
    price = start
    for i in range(n):
        delta = step if i % 2 == 0 else -step * 0.6
        price += price * delta
        candles.append(_candle(price))
    return candles


def test_long_breakout_fires():
    candles = _base_series(60, 100.0, 0.004)
    window_high = max(c["high"] for c in candles[-21:-1])
    # Breakout bar: clears the prior 20-bar high with a volume spike.
    bar = window_high * 1.003
    candles.append(_candle(bar, high=bar * 1.001, low=bar * 0.999, volume=5000.0))

    sig = MomentumBreakoutStrategy().evaluate(candles)
    assert sig.should_enter is True
    assert sig.direction == "long"
    assert sig.reason == "long_breakout"
    assert sig.atr_value is not None


def test_short_breakout_fires():
    # Mild downtrend, then a breakdown bar on volume.
    candles = _base_series(60, 100.0, -0.004)
    window_low = min(c["low"] for c in candles[-21:-1])
    bar = window_low * 0.997
    candles.append(_candle(bar, high=bar * 1.001, low=bar * 0.999, volume=5000.0))

    sig = MomentumBreakoutStrategy().evaluate(candles)
    assert sig.should_enter is True
    assert sig.direction == "short"
    assert sig.reason == "short_breakout"


def test_no_breakout_in_flat_market():
    candles = [_candle(100.0 + (i % 2) * 0.05, volume=1000.0) for i in range(60)]
    sig = MomentumBreakoutStrategy().evaluate(candles)
    assert sig.should_enter is False
    assert sig.reason in {"no_breakout", "no_momentum", "atr_too_low", "low_volume"}


def test_low_volume_blocks_entry():
    candles = _base_series(60, 100.0, 0.003)
    window_high = max(c["high"] for c in candles[-21:-1])
    bar = window_high * 1.01
    # Same breakout price but NO volume expansion -> rejected.
    candles.append(_candle(bar, high=bar * 1.002, low=bar * 0.999, volume=500.0))
    sig = MomentumBreakoutStrategy().evaluate(candles)
    assert sig.should_enter is False
    assert sig.reason == "low_volume"


def test_not_enough_history():
    sig = MomentumBreakoutStrategy().evaluate([_candle(100.0) for _ in range(10)])
    assert sig.reason == "not_enough_history"


def test_short_disabled_when_allow_short_false():
    strat = MomentumBreakoutStrategy()
    strat.allow_short = False
    candles = _base_series(60, 100.0, -0.004)
    window_low = min(c["low"] for c in candles[-21:-1])
    bar = window_low * 0.997
    candles.append(_candle(bar, high=bar * 1.001, low=bar * 0.999, volume=5000.0))
    sig = strat.evaluate(candles)
    assert sig.should_enter is False
