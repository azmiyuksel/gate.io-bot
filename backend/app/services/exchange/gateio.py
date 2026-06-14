import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

import httpx

from app.core.config import get_settings

_INTERVAL_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _interval_seconds(interval: str) -> int:
    """Seconds per candle for a Gate.io interval string (e.g. '1h', '15m', '1d')."""
    try:
        return int(interval[:-1]) * _INTERVAL_UNIT_SECONDS.get(interval[-1], 3600)
    except (ValueError, IndexError):
        return 3600


class OrderBelowMinimum(Exception):
    """Order is below the exchange's minimum base/quote amount (would be rejected)."""


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
        self._pair_cache: dict[str, tuple[dict, float]] = {}
        self._pair_cache_ttl: float = 3600.0  # 1 hour

    async def close(self) -> None:
        await self.client.aclose()

    def __repr__(self) -> str:
        return f"<GateIOClient base_url={self.base_url!r} api_key=***>"

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
                # Honor the server's Retry-After on 429 instead of guessing.
                delay = 2**attempt
                if status == 429:
                    retry_after = exc.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                await asyncio.sleep(min(delay, 60))
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
        return self._parse_candles(data)

    async def candles_range(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        max_pages: int = 40,
    ) -> list[dict]:
        """Fetch every candle in [start, end], paging past Gate.io's 1000-bar
        per-request cap. Without this a long backtest silently truncates to the
        most recent 1000 bars. Returns oldest->newest, de-duplicated."""
        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())
        step = _interval_seconds(interval)
        by_ts: dict[int, dict] = {}
        cursor = end_ts
        for _ in range(max_pages):
            data = await self.request(
                "GET",
                "/spot/candlesticks",
                params={"currency_pair": symbol, "interval": interval, "to": cursor, "limit": 1000},
            )
            parsed = self._parse_candles(data)
            if not parsed:
                break
            for candle in parsed:
                by_ts[int(candle["timestamp"])] = candle
            oldest = min(int(c["timestamp"]) for c in parsed)
            if oldest <= start_ts:
                break
            cursor = oldest - step  # walk the window backwards
        return [by_ts[t] for t in sorted(by_ts) if start_ts <= t <= end_ts]

    @staticmethod
    def _parse_candles(data: list) -> list[dict]:
        result = []
        for item in reversed(data or []):
            close = Decimal(str(item[2]))
            quote_volume = Decimal(str(item[1]))
            # Gate.io v4 returns QUOTE volume at index 1 (and base volume at index 6
            # on newer responses). Expose base volume — the conventional meaning —
            # deriving it from quote/close when the base field is absent.
            if len(item) > 6 and item[6] not in (None, ""):
                base_volume = Decimal(str(item[6]))
            else:
                base_volume = quote_volume / close if close > 0 else Decimal("0")
            result.append(
                {
                    "timestamp": item[0],
                    "volume": base_volume,
                    "quote_volume": quote_volume,
                    "close": close,
                    "high": Decimal(str(item[3])),
                    "low": Decimal(str(item[4])),
                    "open": Decimal(str(item[5])),
                }
            )
        return result

    async def balances(self) -> list[dict]:
        return await self.request("GET", "/spot/accounts")

    async def currency_pair_info(self, symbol: str) -> dict:
        """Cached pair metadata with TTL: precision and min base/quote amounts."""
        cached = self._pair_cache.get(symbol)
        if cached is not None:
            info, ts = cached
            if time.monotonic() - ts < self._pair_cache_ttl:
                return info
        info = await self.request("GET", f"/spot/currency_pairs/{symbol}") or {}
        self._pair_cache[symbol] = (info, time.monotonic())
        return info

    @staticmethod
    def _round_down(value: Decimal, precision: int) -> Decimal:
        """Round DOWN to `precision` decimals (never over-spend / over-sell)."""
        precision = max(int(precision), 0)
        return value.quantize(Decimal(1).scaleb(-precision), rounding=ROUND_DOWN)

    async def _submit_market(self, symbol: str, side: str, amount: Decimal) -> dict:
        # Gate.io spot market orders require an IOC time-in-force.
        return await self.request(
            "POST",
            "/spot/orders",
            json_body={
                "currency_pair": symbol,
                "type": "market",
                "side": side,
                "amount": str(amount),
                "account": "spot",
                "time_in_force": "ioc",
            },
        )

    async def place_market_buy(self, symbol: str, quote_amount: Decimal) -> dict:
        """Market BUY. On Gate.io spot the `amount` is the QUOTE to spend (USDT),
        rounded to the pair's price precision and checked against min_quote_amount."""
        info = await self.currency_pair_info(symbol)
        amount = self._round_down(quote_amount, int(info.get("precision", 8) or 8))
        min_quote = Decimal(str(info.get("min_quote_amount", "0") or "0"))
        if amount <= 0 or amount < min_quote:
            raise OrderBelowMinimum(
                f"{symbol} buy quote {amount} below minimum {min_quote}"
            )
        return await self._submit_market(symbol, "buy", amount)

    async def place_market_sell(self, symbol: str, base_amount: Decimal) -> dict:
        """Market SELL. `amount` is the BASE quantity, rounded to amount_precision
        and checked against min_base_amount."""
        info = await self.currency_pair_info(symbol)
        amount = self._round_down(base_amount, int(info.get("amount_precision", 8) or 8))
        min_base = Decimal(str(info.get("min_base_amount", "0") or "0"))
        if amount <= 0 or amount < min_base:
            raise OrderBelowMinimum(
                f"{symbol} sell base {amount} below minimum {min_base}"
            )
        return await self._submit_market(symbol, "sell", amount)

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
        if not ticker:
            return None
        last = ticker.get("last")
        if last not in (None, "", "0"):
            return Decimal(str(last))
        # Fall back to the bid/ask midpoint when `last` is missing/stale
        # (illiquid pairs or feed gaps).
        bid, ask = ticker.get("highest_bid"), ticker.get("lowest_ask")
        if bid not in (None, "", "0") and ask not in (None, "", "0"):
            return (Decimal(str(bid)) + Decimal(str(ask))) / 2
        return None
