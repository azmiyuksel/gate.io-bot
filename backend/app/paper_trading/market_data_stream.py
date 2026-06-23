import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import websockets

from app.paper_trading.models import MarketData

logger = logging.getLogger(__name__)


class GateIOMarketDataStream:
    def __init__(self, symbols: list[str], buffer_size: int = 1000, market: str = "spot") -> None:
        self.symbols = symbols
        self.buffer: deque[MarketData] = deque(maxlen=buffer_size)
        self.url = "wss://api.gateio.ws/ws/v4/"
        self.running = False
        # Gate.io channels are namespaced by market: `spot.tickers` for spot and
        # `futures.tickers` for USDT-margined perpetuals. Subscribing to spot in a
        # futures simulation makes paper prices diverge from live (basis, funding,
        # perp premium), so the channel must match the simulated market.
        self.channel = "futures.tickers" if market.lower() == "futures" else "spot.tickers"

    async def stream(self) -> AsyncIterator[MarketData]:
        self.running = True
        while self.running:
            try:
                logger.info("Connecting to Gate.io WebSocket: %s (channel=%s)", self.url, self.channel)
                async with websockets.connect(self.url, ping_interval=20) as websocket:
                    await websocket.send(
                        json.dumps(
                            {
                                "time": int(datetime.now(UTC).timestamp()),
                                "channel": self.channel,
                                "event": "subscribe",
                                "payload": self.symbols,
                            }
                        )
                    )
                    logger.info("Subscribed to %s for %d symbols", self.channel, len(self.symbols))
                    async for message in websocket:
                        data = self._parse(message)
                        if data:
                            self.buffer.append(data)
                            yield data
            except Exception as exc:
                logger.warning("WebSocket error, reconnecting in 3s: %s", exc)
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
        # A ticker tick has no intra-bar range; leave high/low unset rather than
        # filling them with the 24h high/low, which downstream code would wrongly
        # treat as a single bar's range (inflating slippage and tripping filters).
        return MarketData(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            price=float(price),
            volume=float(result.get("base_volume") or 0),
        )

    def latest_or_missing(self, symbol: str) -> MarketData | None:
        for item in reversed(self.buffer):
            if item.symbol == symbol:
                return item
        return None
