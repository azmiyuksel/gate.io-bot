"""Time-continuity / gap detection for candle streams.

Detects missing candles (holes in an otherwise regular series), a delayed feed
(the most recent candle is older than it should be) and websocket-disconnect
gaps (a single jump larger than several intervals). Optionally interpolates
small holes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market_data_quality.models import CandleData

# Supported timeframe -> seconds.
_TIMEFRAME_SECONDS = {
    "1s": 1, "10s": 10, "30s": 30,
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200,
    "1d": 86400, "1w": 604800,
}


def timeframe_seconds(timeframe: str) -> int:
    return _TIMEFRAME_SECONDS.get(timeframe, 3600)


@dataclass
class GapReport:
    missing_count: int
    missing_timestamps: list[datetime]
    duplicate_count: int
    feed_delayed: bool
    feed_lag_seconds: float
    disconnect_gap: bool


class GapDetector:
    def __init__(self, timeframe: str = "1h", disconnect_multiple: int = 5) -> None:
        self.timeframe = timeframe
        self.interval = timeframe_seconds(timeframe)
        self.disconnect_multiple = disconnect_multiple

    def analyze(self, candles: list[CandleData], now: datetime | None = None) -> GapReport:
        if not candles:
            return GapReport(0, [], 0, False, 0.0, False)

        ordered = sorted(candles, key=lambda c: c.timestamp)
        step = timedelta(seconds=self.interval)
        missing: list[datetime] = []
        duplicates = 0
        disconnect = False

        for prev, cur in zip(ordered, ordered[1:]):
            delta = (cur.timestamp - prev.timestamp).total_seconds()
            if delta == 0:
                duplicates += 1
                continue
            steps = round(delta / self.interval)
            if steps > 1:
                # Fill in the timestamps that should have existed.
                for i in range(1, steps):
                    missing.append(prev.timestamp + step * i)
                if steps >= self.disconnect_multiple:
                    disconnect = True

        now = now or datetime.now(UTC)
        feed_lag = (now - ordered[-1].timestamp).total_seconds()
        feed_delayed = feed_lag > self.interval * 2

        return GapReport(
            missing_count=len(missing),
            missing_timestamps=missing,
            duplicate_count=duplicates,
            feed_delayed=feed_delayed,
            feed_lag_seconds=feed_lag,
            disconnect_gap=disconnect,
        )

    @staticmethod
    def interpolate(prev: CandleData, nxt: CandleData, timestamp: datetime) -> CandleData:
        """Linear interpolation for a single missing candle between two known ones."""
        mid = (prev.close + nxt.open) / Decimal("2")
        return CandleData(
            symbol=prev.symbol,
            timeframe=prev.timeframe,
            timestamp=timestamp,
            open=prev.close,
            high=max(prev.close, nxt.open),
            low=min(prev.close, nxt.open),
            close=mid,
            volume=Decimal("0"),
            source=f"{prev.source}:interpolated",
        )
