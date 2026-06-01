"""Backtest-side data quality helpers (no database required).

Two purposes:

1. Apply the *same* structural validation + spike rules used in live trading to a
   historical candle series, so a backtest never trades on candles that the live
   pipeline would have rejected.
2. Inject controlled corruption (spikes, gaps, delays) into clean data for
   robustness testing of strategies on noisy feeds.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal

from app.market_data_quality.models import CandleData, RepairAction
from app.market_data_quality.spike_detector import SpikeDetector
from app.market_data_quality.validator import CandleValidator


@dataclass
class CleanResult:
    clean: list[CandleData]
    dropped: int
    flagged: int
    total: int


class BacktestDataQuality:
    def __init__(self, spike_threshold_pct: float = 0.10, spike_mode: str = "flag") -> None:
        self.validator = CandleValidator(spike_threshold_pct=spike_threshold_pct)
        self.spike = SpikeDetector(threshold_pct=spike_threshold_pct, mode=spike_mode)

    def clean(self, candles: list[CandleData]) -> CleanResult:
        ordered = sorted(candles, key=lambda c: c.timestamp)
        clean: list[CandleData] = []
        dropped = flagged = 0
        previous: CandleData | None = None

        for candle in ordered:
            validation = self.validator.validate(candle, previous)
            # Structural failures -> drop, do not advance "previous".
            if not validation.is_valid and any(
                code.value != "EXCESSIVE_MOVE" for code in validation.codes
            ):
                dropped += 1
                continue

            spike = self.spike.detect(candle, previous)
            if spike.is_spike:
                if spike.repair_action == RepairAction.drop:
                    dropped += 1
                    continue
                if spike.repaired is not None:
                    candle = spike.repaired
                flagged += 1

            clean.append(candle)
            previous = candle

        return CleanResult(clean=clean, dropped=dropped, flagged=flagged, total=len(ordered))

    # ------------------------------------------------------------------
    # Dirty-data scenario simulation for robustness testing
    # ------------------------------------------------------------------
    @staticmethod
    def inject_spikes(
        candles: list[CandleData], probability: float = 0.02, magnitude: float = 0.25, seed: int = 7
    ) -> list[CandleData]:
        rng = random.Random(seed)
        out: list[CandleData] = []
        for c in candles:
            if rng.random() < probability:
                factor = Decimal("1") + Decimal(str(magnitude)) * (1 if rng.random() < 0.5 else -1)
                spiked_close = c.close * factor
                out.append(
                    CandleData(
                        symbol=c.symbol,
                        timeframe=c.timeframe,
                        timestamp=c.timestamp,
                        open=c.open,
                        high=max(c.high, spiked_close),
                        low=min(c.low, spiked_close),
                        close=spiked_close,
                        volume=c.volume,
                        source=f"{c.source}:spiked",
                    )
                )
            else:
                out.append(c)
        return out

    @staticmethod
    def drop_candles(
        candles: list[CandleData], probability: float = 0.05, seed: int = 7
    ) -> list[CandleData]:
        rng = random.Random(seed)
        return [c for c in candles if rng.random() >= probability]
