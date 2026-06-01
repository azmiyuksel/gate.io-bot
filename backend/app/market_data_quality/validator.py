"""Deterministic per-candle validation rules.

These are cheap, exchange-agnostic structural checks that must pass before a
candle is trusted. Statistical/contextual anomaly detection lives in
``anomaly_detector`` and the specialized detectors; this module only answers
"is this candle internally well-formed?".
"""
from __future__ import annotations

from decimal import Decimal

from app.market_data_quality.models import (
    CandleData,
    ValidationCode,
    ValidationResult,
)


class CandleValidator:
    def __init__(self, spike_threshold_pct: float = 0.10) -> None:
        self.spike_threshold = Decimal(str(spike_threshold_pct))

    def validate(
        self, candle: CandleData, previous: CandleData | None = None
    ) -> ValidationResult:
        result = ValidationResult(is_valid=True)

        self._check_positive_prices(candle, result)
        self._check_non_negative_volume(candle, result)
        self._check_ohlc_consistency(candle, result)
        if previous is not None:
            self._check_duplicate_timestamp(candle, previous, result)
            self._check_price_movement(candle, previous, result)

        return result

    # --- B) Zero / Negative Values ---
    def _check_positive_prices(self, c: CandleData, result: ValidationResult) -> None:
        for name in ("open", "high", "low", "close"):
            if getattr(c, name) <= 0:
                result.add(ValidationCode.non_positive_price, f"{name}={getattr(c, name)} <= 0")

    def _check_non_negative_volume(self, c: CandleData, result: ValidationResult) -> None:
        if c.volume < 0:
            result.add(ValidationCode.negative_volume, f"volume={c.volume} < 0")

    # --- A) OHLC Consistency ---
    def _check_ohlc_consistency(self, c: CandleData, result: ValidationResult) -> None:
        # High must be the maximum of (open, high, low, close).
        if c.high < max(c.open, c.close, c.low):
            result.add(
                ValidationCode.high_below_components,
                f"high={c.high} below max(open={c.open}, close={c.close}, low={c.low})",
            )
        # Low must be the minimum.
        if c.low > min(c.open, c.close, c.high):
            result.add(
                ValidationCode.low_above_components,
                f"low={c.low} above min(open={c.open}, close={c.close}, high={c.high})",
            )

    # --- C) Time Continuity ---
    def _check_duplicate_timestamp(
        self, c: CandleData, prev: CandleData, result: ValidationResult
    ) -> None:
        if c.timestamp == prev.timestamp:
            result.add(
                ValidationCode.duplicate_timestamp,
                f"duplicate timestamp {c.timestamp.isoformat()}",
            )

    # --- D) Price Movement Limits ---
    def _check_price_movement(
        self, c: CandleData, prev: CandleData, result: ValidationResult
    ) -> None:
        if prev.close <= 0:
            return
        change = abs(c.close - prev.close) / prev.close
        if change > self.spike_threshold:
            result.add(
                ValidationCode.excessive_move,
                f"close move {change:.4f} > threshold {self.spike_threshold}",
            )
