import asyncio
import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings


class RateLimiter:
    def __init__(self, requests_per_second: int) -> None:
        self.delay = 1 / max(requests_per_second, 1)
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def wait(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self.delay:
                await asyncio.sleep(self.delay - elapsed)
            self._last_call = time.monotonic()


class GateIOClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.gateio_base_url.rstrip("/")
        self.api_key = settings.gateio_api_key
        self.api_secret = settings.gateio_api_secret
        self.limiter = RateLimiter(settings.gateio_requests_per_second)
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=15)

    async def close(self) -> None:
        await self.client.aclose()

    def _sign(self, method: str, path: str, query: str = "", body: str = "") -> dict[str, str]:
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha512(body.encode()).hexdigest()
        payload = "\n".join([method.upper(), path, query, body_hash, timestamp])
        signature = hmac.new(
            self.api_secret.encode(), payload.encode(), hashlib.sha512
        ).hexdigest()
        return {"KEY": self.api_key, "Timestamp": timestamp, "SIGN": signature}

    # Transient transport failures and HTTP 429/5xx are retried; other 4xx
    # (auth, bad request, not found) fail fast since retrying cannot help.
    _RETRYABLE_NETWORK = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)

    async def request(
        self, method: str, path: str, *, params: dict | None = None, json_body: dict | None = None
    ) -> Any:
        body = json.dumps(json_body, separators=(",", ":")) if json_body else ""
        query = str(httpx.QueryParams(params or {}))
        attempts = 3
        for attempt in range(attempts):
            await self.limiter.wait()
            # Re-sign on every attempt: the signature embeds a timestamp that
            # the exchange rejects once it drifts past its tolerance window.
            headers = (
                self._sign(method, path, query, body)
                if self.api_key and self.api_secret
                else {}
            )
            try:
                response = await self.client.request(
                    method, path, params=params, content=body or None, headers=headers
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                retryable = status == 429 or status >= 500
                if not retryable or attempt == attempts - 1:
                    raise
                await asyncio.sleep(2**attempt)
            except self._RETRYABLE_NETWORK:
                if attempt == attempts - 1:
                    raise
                await asyncio.sleep(2**attempt)

    async def candles(self, symbol: str, interval: str = "1h", limit: int = 240) -> list[dict]:
        data = await self.request(
            "GET",
            "/spot/candlesticks",
            params={"currency_pair": symbol, "interval": interval, "limit": limit},
        )
        return [
            {
                "timestamp": item[0],
                "volume": item[1],
                "close": Decimal(str(item[2])),
                "high": Decimal(str(item[3])),
                "low": Decimal(str(item[4])),
                "open": Decimal(str(item[5])),
            }
            for item in reversed(data)
        ]

    async def balances(self) -> list[dict]:
        return await self.request("GET", "/spot/accounts")

    async def place_market_order(self, symbol: str, side: str, amount: Decimal) -> dict:
        return await self.request(
            "POST",
            "/spot/orders",
            json_body={
                "currency_pair": symbol,
                "type": "market",
                "side": side,
                "amount": str(amount),
                "account": "spot",
            },
        )

    async def get_order(self, symbol: str, order_id: str) -> dict:
        return await self.request("GET", f"/spot/orders/{order_id}", params={"currency_pair": symbol})

    async def open_orders(self, symbol: str | None = None) -> list[dict]:
        params = {"currency_pair": symbol} if symbol else None
        return await self.request("GET", "/spot/open_orders", params=params)

    async def ticker(self, symbol: str) -> dict | None:
        data = await self.request("GET", "/spot/tickers", params={"currency_pair": symbol})
        return data[0] if data else None

    async def last_price(self, symbol: str) -> Decimal | None:
        ticker = await self.ticker(symbol)
        if not ticker or ticker.get("last") is None:
            return None
        return Decimal(str(ticker["last"]))
