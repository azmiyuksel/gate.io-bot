"""Volume-based anomaly detection: volume spikes and sudden liquidity drops."""
from __future__ import annotations

import statistics

from app.market_data_quality.models import AnomalyFinding, AnomalyType, CandleData


class VolumeAnalyzer:
    def __init__(
        self,
        spike_multiple: float = 8.0,
        liquidity_drop_pct: float = 0.10,
        window: int = 50,
    ) -> None:
        self.spike_multiple = spike_multiple
        self.liquidity_drop_pct = liquidity_drop_pct
        self.window = window

    def analyze(self, candle: CandleData, history: list[CandleData]) -> list[AnomalyFinding]:
        findings: list[AnomalyFinding] = []
        volumes = [float(c.volume) for c in history[-self.window :] if c.volume is not None]
        if len(volumes) < 10:
            return findings

        mean = statistics.fmean(volumes)
        current = float(candle.volume)
        if mean <= 0:
            return findings

        ratio = current / mean

        # Volume spike: unusually high traded volume.
        if ratio >= self.spike_multiple:
            findings.append(
                AnomalyFinding(
                    anomaly_type=AnomalyType.volume_spike,
                    severity="CRITICAL" if ratio >= self.spike_multiple * 2 else "WARNING",
                    detail=f"volume {current:.4f} is {ratio:.1f}x rolling mean {mean:.4f}",
                    observed_value=ratio,
                    threshold_value=self.spike_multiple,
                    detection_method="rolling_mean",
                )
            )

        # Sudden liquidity drop: volume collapses far below normal.
        if ratio <= self.liquidity_drop_pct:
            findings.append(
                AnomalyFinding(
                    anomaly_type=AnomalyType.liquidity_drop,
                    severity="WARNING",
                    detail=f"volume {current:.4f} is {ratio:.2%} of rolling mean {mean:.4f}",
                    observed_value=ratio,
                    threshold_value=self.liquidity_drop_pct,
                    detection_method="rolling_mean",
                )
            )

        return findings
