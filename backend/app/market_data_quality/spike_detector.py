"""Single-candle price spike detection and filtering.

A spike is a price move beyond a configurable threshold relative to the previous
close. Three handling modes are supported per the spec:

* ``flag``   - mark as anomaly, keep the candle (default, safest for audit)
* ``smooth`` - clamp the offending value back toward the threshold boundary
* ``ignore`` - drop the candle entirely
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.market_data_quality.models import (
    AnomalyFinding,
    AnomalyType,
    CandleData,
    RepairAction,
)


@dataclass
class SpikeResult:
    is_spike: bool
    change_pct: float
    direction: str  # up | down | flat
    finding: AnomalyFinding | None
    repaired: CandleData | None
    repair_action: RepairAction


class SpikeDetector:
    def __init__(self, threshold_pct: float = 0.10, mode: str = "flag") -> None:
        self.threshold = Decimal(str(threshold_pct))
        self.mode = mode if mode in ("flag", "smooth", "ignore") else "flag"

    def detect(self, candle: CandleData, previous: CandleData | None) -> SpikeResult:
        if previous is None or previous.close <= 0:
            return SpikeResult(False, 0.0, "flat", None, None, RepairAction.none)

        change = (candle.close - previous.close) / previous.close
        magnitude = abs(change)
        if magnitude <= self.threshold:
            return SpikeResult(False, float(change), "flat", None, None, RepairAction.none)

        direction = "up" if change > 0 else "down"
        anomaly_type = AnomalyType.flash_pump if direction == "up" else AnomalyType.flash_crash
        severity = "CRITICAL" if magnitude > self.threshold * 2 else "WARNING"
        finding = AnomalyFinding(
            anomaly_type=anomaly_type,
            severity=severity,
            detail=f"price spike {change:.4f} ({direction}) > threshold {self.threshold}",
            observed_value=float(magnitude),
            threshold_value=float(self.threshold),
            detection_method="spike_threshold",
        )

        repaired, action = self._apply_mode(candle, previous, change)
        return SpikeResult(True, float(change), direction, finding, repaired, action)

    def _apply_mode(
        self, candle: CandleData, previous: CandleData, change: Decimal
    ) -> tuple[CandleData | None, RepairAction]:
        if self.mode == "flag":
            return candle, RepairAction.flag_uncertain
        if self.mode == "ignore":
            return None, RepairAction.drop
        # smooth: clamp close to the threshold boundary relative to previous close.
        bound = self.threshold if change > 0 else -self.threshold
        smoothed_close = previous.close * (Decimal("1") + bound)
        repaired = CandleData(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            timestamp=candle.timestamp,
            open=candle.open,
            high=max(candle.open, smoothed_close),
            low=min(candle.open, smoothed_close),
            close=smoothed_close,
            volume=candle.volume,
            source=f"{candle.source}:smoothed",
        )
        return repaired, RepairAction.interpolate
