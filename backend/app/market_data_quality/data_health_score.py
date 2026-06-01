"""Weighted 0-100 data health score.

score = 0.30 * consistency
      + 0.30 * completeness
      + 0.20 * anomaly_inverse
      + 0.20 * latency

Each component is itself a 0-100 sub-score so the weights are easy to reason
about. The score maps to a category (Excellent/Good/Risky/Unreliable) and a
trading gate status (Clean/Degraded/Invalid).
"""
from __future__ import annotations

from app.market_data_quality.models import (
    ANOMALY_INVERSE_WEIGHT,
    COMPLETENESS_WEIGHT,
    CONSISTENCY_WEIGHT,
    LATENCY_WEIGHT,
    HealthScore,
    category_for_score,
    trade_status_for_score,
)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


class DataHealthScorer:
    @staticmethod
    def consistency_score(total: int, invalid: int) -> float:
        if total <= 0:
            return 100.0
        return _clamp(100.0 * (1.0 - invalid / total))

    @staticmethod
    def completeness_score(expected: int, missing: int) -> float:
        if expected <= 0:
            return 100.0
        return _clamp(100.0 * (1.0 - missing / expected))

    @staticmethod
    def anomaly_inverse_score(total: int, anomalies: int) -> float:
        if total <= 0:
            return 100.0
        # Each anomaly costs proportionally; fully penalized when every candle is anomalous.
        return _clamp(100.0 * (1.0 - min(anomalies, total) / total))

    @staticmethod
    def latency_score(feed_lag_seconds: float, interval_seconds: float) -> float:
        if interval_seconds <= 0:
            return 100.0
        # Full marks up to one interval of lag, decaying to 0 by 5 intervals.
        ratio = feed_lag_seconds / interval_seconds
        if ratio <= 1.0:
            return 100.0
        return _clamp(100.0 * (1.0 - (ratio - 1.0) / 4.0))

    def compute(
        self,
        *,
        total_candles: int,
        invalid_candles: int,
        expected_candles: int,
        missing_candles: int,
        anomalies: int,
        feed_lag_seconds: float,
        interval_seconds: float,
    ) -> HealthScore:
        consistency = self.consistency_score(total_candles, invalid_candles)
        completeness = self.completeness_score(expected_candles, missing_candles)
        anomaly_inv = self.anomaly_inverse_score(total_candles, anomalies)
        latency = self.latency_score(feed_lag_seconds, interval_seconds)

        score = _clamp(
            CONSISTENCY_WEIGHT * consistency
            + COMPLETENESS_WEIGHT * completeness
            + ANOMALY_INVERSE_WEIGHT * anomaly_inv
            + LATENCY_WEIGHT * latency
        )
        return HealthScore(
            score=round(score, 2),
            consistency_score=round(consistency, 2),
            completeness_score=round(completeness, 2),
            anomaly_inverse_score=round(anomaly_inv, 2),
            latency_score=round(latency, 2),
            category=category_for_score(score),
            trade_status=trade_status_for_score(score),
        )
