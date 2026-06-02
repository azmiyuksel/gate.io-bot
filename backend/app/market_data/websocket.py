"""Gate.io spot WebSocket client feeding the shared price cache.

Subscribes to ``spot.tickers`` for the configured symbols and keeps the latest
traded price in :data:`app.market_data.price_cache.price_cache`. Auto-reconnects
with exponential backoff so the live engine always has a fresh mark price
without polling REST on every cycle.
"""
from __future__ import annotations

import asyncio
import json
import time
from decimal import Decimal

import websockets

from app.core.config import get_settings
from app.market_data.price_cache import price_cache


class GateIOWebSocketClient:
    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols
        self.settings = get_settings()
        self.url = self.settings.gateio_ws_url
        self._running = False

    def _subscribe_message(self) -> str:
        return json.dumps(
            {
                "time": int(time.time()),
                "channel": "spot.tickers",
                "event": "subscribe",
                "payload": self.symbols,
            }
        )

    @staticmethod
    def _handle_message(raw: str) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return
        if message.get("channel") != "spot.tickers" or message.get("event") != "update":
            return
        result = message.get("result") or {}
        symbol = result.get("currency_pair")
        last = result.get("last")
        if symbol and last is not None:
            price_cache.set(symbol, Decimal(str(last)))

    async def run(self) -> None:
        """Connect and stream forever, reconnecting on failure."""
        self._running = True
        backoff = 1
        while self._running:
            try:
                # ping_timeout closes a dead connection if the server stops
                # answering pings, so reconnect logic kicks in instead of hanging.
                async with websockets.connect(
                    self.url, ping_interval=20, ping_timeout=10, close_timeout=5
                ) as ws:
                    await ws.send(self._subscribe_message())
                    backoff = 1
                    async for raw in ws:
                        self._handle_message(raw)
            except asyncio.CancelledError:
                self._running = False
                raise
            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def stop(self) -> None:
        self._running = False
