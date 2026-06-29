import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import websockets

from app.paper_trading.models import MarketData

logger = logging.getLogger(__name__)

# EWMA window of 5 minutes (~300 ticks at 1 tick/s). The alpha below gives a
# half-life of ~1 minute, a reasonable proxy of "available depth now" without
# being dominated by a single large print. The simulator's impact / partial-fill
# checks rely on this being a CURRENT bar-style volume, not the 24h cumulative
# volume Gate.io's ticker channel streams (which massively over-liquifies the
# book and makes market impact nearly never trigger).
_EWMA_HALF_LIFE_TICKS = 60
_EWMA_ALPHA = 1.0 - 2.0 ** (-1.0 / _EWMA_HALF_LIFE_TICKS)


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
        # Parallel trades channel subscription for real-time bar-volume estimation.
        # The ticker channel only carries the 24h cumulative `base_volume`, which
        # massively overstates available depth — the trades channel gives each
        # print's `amount` so we can EWMA a ~5-minute rolling bar-style volume per
        # symbol that the simulator uses for impact / partial-fill caps.
        self.trades_channel = "futures.trades" if market.lower() == "futures" else "spot.trades"
        self._ewma_volume: dict[str, float] = {}

    async def stream(self) -> AsyncIterator[MarketData]:
        self.running = True
        while self.running:
            try:
                logger.info(
                    "Connecting to Gate.io WebSocket: %s (channels=%s/%s)",
                    self.url, self.channel, self.trades_channel,
                )
                async with websockets.connect(self.url, ping_interval=20) as websocket:
                    # Subscribe to BOTH the tickers and the trades channels.
                    # Two separate subscribe frames so Gate.io assigns them to
                    # the same multiplexed WS — a single subscribe payload with
                    # two channels would be silently rejected.
                    for channel in (self.channel, self.trades_channel):
                        await websocket.send(
                            json.dumps(
                                {
                                    "time": int(datetime.now(UTC).timestamp()),
                                    "channel": channel,
                                    "event": "subscribe",
                                    "payload": self.symbols,
                                }
                            )
                        )
                    logger.info("Subscribed to %s + %s for %d symbols", self.channel, self.trades_channel, len(self.symbols))
                    async for message in websocket:
                        # Process trades first to update EWMA volume, then tickers
                        # to emit MarketData with that fresh volume attached.
                        self._ingest_trades(message)
                        data = self._parse_ticker(message)
                        if data:
                            self.buffer.append(data)
                            yield data
            except Exception as exc:
                logger.warning("WebSocket error, reconnecting in 3s: %s", exc)
                await asyncio.sleep(3)

    def stop(self) -> None:
        self.running = False

    def _ingest_trades(self, raw: str) -> None:
        """Update the EWMA per-symbol bar volume from a `trades` channel frame."""
        try:
            payload = json.loads(raw)
        except Exception:
            return
        channel = payload.get("channel")
        if channel != self.trades_channel:
            return
        result = payload.get("result") or {}
        # Gate.io trades result: {"id", "create_time_ms", "currency_pair",
        # "amount", "price", "side"}. `amount` is base-asset quantity traded.
        symbol = result.get("currency_pair")
        amount = result.get("amount")
        if not symbol or amount is None:
            return
        try:
            amt = float(amount)
        except (TypeError, ValueError):
            return
        prev = self._ewma_volume.get(symbol)
        # Incremental EWMA: each trade print is a per-tick sample. The smooth
        # half-life keeps a single large print from dominating the depth proxy.
        # First sample seeds the EWMA at its own value (warm-start) so the depth
        # proxy doesn't sit at ~0 until the EWMA slowly converge.
        if prev is None:
            self._ewma_volume[symbol] = amt
        else:
            self._ewma_volume[symbol] = _EWMA_ALPHA * amt + (1.0 - _EWMA_ALPHA) * prev

    def _parse_ticker(self, raw: str) -> MarketData | None:
        payload = json.loads(raw)
        result = payload.get("result")
        if not result or payload.get("channel") != self.channel:
            return None
        price = result.get("last")
        symbol = result.get("currency_pair")
        if not price or not symbol:
            return None
        # A ticker tick has no intra-bar range; leave high/low unset rather than
        # filling them with the 24h high/low, which downstream code would wrongly
        # treat as a single bar's range (inflating slippage and tripping filters).
        # Use the EWMA volume from the trades channel when available; fall back to
        # zero so the simulator applies its min_depth floor.
        volume = self._ewma_volume.get(symbol, 0.0)
        return MarketData(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            price=float(price),
            volume=volume,
            bid=float(result["last_bid"]) if result.get("last_bid") else None,
            ask=float(result["last_ask"]) if result.get("last_ask") else None,
        )

    def latest_or_missing(self, symbol: str) -> MarketData | None:
        for item in reversed(self.buffer):
            if item.symbol == symbol:
                return item
        return None