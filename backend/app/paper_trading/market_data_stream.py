import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import websockets

from app.paper_trading.models import MarketData


class GateIOMarketDataStream:
    def __init__(self, symbols: list[str], buffer_size: int = 1000) -> None:
        self.symbols = symbols
        self.buffer: deque[MarketData] = deque(maxlen=buffer_size)
        self.url = "wss://api.gateio.ws/ws/v4/"
        self.running = False

    async def stream(self) -> AsyncIterator[MarketData]:
        self.running = True
        while self.running:
            try:
                async with websockets.connect(self.url, ping_interval=20) as websocket:
                    await websocket.send(
                        json.dumps(
                            {
                                "time": int(datetime.now(UTC).timestamp()),
                                "channel": "spot.tickers",
                                "event": "subscribe",
                                "payload": self.symbols,
                            }
                        )
                    )
                    async for message in websocket:
                        data = self._parse(message)
                        if data:
                            self.buffer.append(data)
                            yield data
            except Exception:
                await asyncio.sleep(3)

    def stop(self) -> None:
        self.running = False

    def _parse(self, raw: str) -> MarketData | None:
        payload = json.loads(raw)
        result = payload.get("result")
        if not result:
            return None
        price = result.get("last")
        symbol = result.get("currency_pair")
        if not price or not symbol:
            return None
        return MarketData(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            price=float(price),
            volume=float(result.get("base_volume") or 0),
            high=float(result.get("high_24h") or price),
            low=float(result.get("low_24h") or price),
        )

    def latest_or_missing(self, symbol: str) -> MarketData | None:
        for item in reversed(self.buffer):
            if item.symbol == symbol:
                return item
        return None
