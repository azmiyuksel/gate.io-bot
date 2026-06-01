"""OHLCV ingestion: pull candles from Gate.io and upsert into ``historical_candles``.

Keeps the local candle store (used by backtests, walk-forward and the regime
engine) continuously fed so analytics do not depend on ad-hoc REST pulls.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import HistoricalCandle
from app.services.exchange.gateio import GateIOClient


def _to_datetime(timestamp) -> datetime:
    return datetime.fromtimestamp(int(timestamp), UTC)


class MarketDataIngestion:
    def __init__(self, db: Session, client: GateIOClient) -> None:
        self.db = db
        self.client = client
        self.settings = get_settings()

    async def ingest(self, symbol: str, interval: str | None = None, limit: int = 240) -> int:
        interval = interval or self.settings.market_data_interval
        candles = await self.client.candles(symbol, interval=interval, limit=limit)
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

    async def ingest_all(self, symbols: list[str], interval: str | None = None) -> dict[str, int]:
        return {symbol: await self.ingest(symbol, interval) for symbol in symbols}
