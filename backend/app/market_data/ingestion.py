"""OHLCV ingestion: pull candles from Gate.io and upsert into ``historical_candles``.

Keeps the local candle store (used by backtests, walk-forward and the regime
engine) continuously fed so analytics do not depend on ad-hoc REST pulls.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.market_data_quality.engine import MarketDataQualityEngine
from app.models.entities import HistoricalCandle
from app.services.exchange.gateio import GateIOClient


def _to_datetime(timestamp) -> datetime:
    return datetime.fromtimestamp(int(timestamp), UTC)


class MarketDataIngestion:
    def __init__(self, db: Session, client: GateIOClient, quality_check: bool = True) -> None:
        self.db = db
        self.client = client
        self.settings = get_settings()
        self.quality_check = quality_check

    async def ingest(self, symbol: str, interval: str | None = None, limit: int = 240) -> int:
        interval = interval or self.settings.market_data_interval
        candles = await self.client.candles(symbol, interval=interval, limit=limit)
        if not candles:
            return 0

        # Run the raw feed through the quality pipeline; only clean candles are
        # promoted to the historical store used by backtests/regime/strategies.
        if self.quality_check:
            candles = self._clean_through_quality(symbol, interval, candles)
            if not candles:
                return 0

        timestamps = [_to_datetime(c["timestamp"]) for c in candles]
        existing = {
            ts
            for (ts,) in self.db.query(HistoricalCandle.timestamp)
            .filter(HistoricalCandle.symbol == symbol)
            .filter(HistoricalCandle.timeframe == interval)
            .filter(HistoricalCandle.timestamp.in_(timestamps))
            .all()
        }

        inserted = 0
        for candle, ts in zip(candles, timestamps):
            if ts in existing:
                continue
            self.db.add(
                HistoricalCandle(
                    symbol=symbol,
                    timeframe=interval,
                    timestamp=ts,
                    open=Decimal(str(candle["open"])),
                    high=Decimal(str(candle["high"])),
                    low=Decimal(str(candle["low"])),
                    close=Decimal(str(candle["close"])),
                    volume=Decimal(str(candle["volume"])),
                    source="gateio",
                )
            )
            inserted += 1

        self.db.commit()
        return inserted

    def _clean_through_quality(self, symbol: str, interval: str, candles: list[dict]) -> list[dict]:
        """Validate/clean raw candles via the quality engine, returning clean dicts."""
        engine = MarketDataQualityEngine(self.db)
        result = engine.ingest(candles, symbol, interval, source="gateio")
        clean = engine.emit_clean_data(result)
        return [
            {
                "timestamp": int(c.timestamp.timestamp()),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in clean
        ]

    async def ingest_all(self, symbols: list[str], interval: str | None = None) -> dict[str, int]:
        return {symbol: await self.ingest(symbol, interval) for symbol in symbols}
