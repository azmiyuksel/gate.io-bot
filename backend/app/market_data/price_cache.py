"""Process-wide in-memory cache of the latest traded price per symbol.

The WebSocket client (`market_data.websocket`) writes to it; the account,
reconciliation and trading layers read from it to avoid extra REST calls.
Thread-safe for the simple read/write pattern used here.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal


class PriceCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prices: dict[str, Decimal] = {}
        self._updated_at: dict[str, datetime] = {}

    def set(self, symbol: str, price: Decimal) -> None:
        with self._lock:
            self._prices[symbol] = price
            self._updated_at[symbol] = datetime.now(UTC)

    def get(self, symbol: str) -> Decimal | None:
        with self._lock:
            return self._prices.get(symbol)

    def updated_at(self, symbol: str) -> datetime | None:
        with self._lock:
            return self._updated_at.get(symbol)

    def is_fresh(self, symbol: str, max_age_seconds: float = 60.0) -> bool:
        ts = self.updated_at(symbol)
        if ts is None:
            return False
        return (datetime.now(UTC) - ts).total_seconds() <= max_age_seconds

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {symbol: float(price) for symbol, price in self._prices.items()}


# Shared singleton used across the process.
price_cache = PriceCache()
