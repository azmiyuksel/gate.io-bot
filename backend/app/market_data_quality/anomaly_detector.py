"""Statistical / ML anomaly detection over a rolling candle window.

Layers, cheapest first:

1. Z-score on log returns (price spike / flash move).
2. Rolling-mean deviation on the close.
3. Optional Isolation Forest over [return, range, volume] features.

The specialized price-spike and volume detectors complement this with
threshold-based rules; this module catches context-relative outliers.
"""
from __future__ import annotations

import math
import statistics

from app.market_data_quality.models import AnomalyFinding, AnomalyType, CandleData


class AnomalyDetector:
    def __init__(
        self,
        zscore_threshold: float = 5.0,
        window: int = 100,
        enable_ml: bool = True,
    ) -> None:
        self.zscore_threshold = zscore_threshold
        self.window = window
        self.enable_ml = enable_ml

    def detect(self, candle: CandleData, history: list[CandleData]) -> list[AnomalyFinding]:
        findings: list[AnomalyFinding] = []
        window = history[-self.window :]
        if len(window) < 20:
            return findings

        findings.extend(self._zscore_return(candle, window))
        if self.enable_ml:
            ml = self._isolation_forest(candle, window)
            if ml is not None:
                findings.append(ml)
        return findings

    def _last_return_z(self, candle: CandleData, window: list[CandleData]) -> float:
        """Z-score of the latest candle's log-return vs the window distribution."""
        closes = [float(c.close) for c in window]
        returns = self._log_returns(closes)
        if len(returns) < 10 or window[-1].close <= 0 or candle.close <= 0:
            return 0.0
        mean = statistics.fmean(returns)
        std = statistics.pstdev(returns)
        if std <= 0:
            return 0.0
        last_ret = math.log(float(candle.close) / float(window[-1].close))
        return (last_ret - mean) / std

    @staticmethod
    def _log_returns(closes: list[float]) -> list[float]:
        returns = []
        for prev, cur in zip(closes, closes[1:]):
            if prev > 0 and cur > 0:
                returns.append(math.log(cur / prev))
        return returns

    def _zscore_return(self, candle: CandleData, window: list[CandleData]) -> list[AnomalyFinding]:
        z = self._last_return_z(candle, window)
        if z == 0.0 or abs(z) < self.zscore_threshold:
            return []
        atype = AnomalyType.flash_pump if z > 0 else AnomalyType.flash_crash
        return [
            AnomalyFinding(
                anomaly_type=atype,
                severity="CRITICAL" if abs(z) >= self.zscore_threshold * 1.5 else "WARNING",
                detail=f"return z-score {z:.2f} exceeds {self.zscore_threshold}",
                observed_value=abs(z),
                threshold_value=self.zscore_threshold,
                detection_method="zscore",
            )
        ]

    def _isolation_forest(
        self, candle: CandleData, window: list[CandleData]
    ) -> AnomalyFinding | None:
        # Isolation Forest inherently labels ~contamination fraction of points as
        # outliers, so on its own it false-positives on smooth data. Require mild
        # statistical corroboration (the latest move is at least a 2-sigma return)
        # before trusting the ML flag.
        if abs(self._last_return_z(candle, window)) < 2.0:
            return None
        try:
            import numpy as np
            from sklearn.ensemble import IsolationForest
        except Exception:
            return None

        feats = []
        prev_close = None
        for c in window:
            close = float(c.close)
            ret = 0.0 if not prev_close or prev_close <= 0 else (close - prev_close) / prev_close
            rng = (float(c.high) - float(c.low)) / close if close > 0 else 0.0
            feats.append([ret, rng, float(c.volume)])
            prev_close = close
        if len(feats) < 30:
            return None

        try:
            X = np.array(feats, dtype=float)
            model = IsolationForest(contamination=0.02, random_state=42, n_estimators=80)
            model.fit(X)
            score = model.predict(X[-1].reshape(1, -1))[0]
        except Exception:
            return None

        if score == -1:
            return AnomalyFinding(
                anomaly_type=AnomalyType.isolation_forest,
                severity="WARNING",
                detail="isolation forest flagged latest candle as outlier",
                detection_method="isolation_forest",
            )
        return None
