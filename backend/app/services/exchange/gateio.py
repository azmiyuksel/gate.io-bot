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
    _RETRYABLE_NETWORK = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError)

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

    async def candles(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 240,
        drop_unclosed: bool = False,
        market: str = "spot",
    ) -> list[dict]:
        # Futures and spot have DIFFERENT candles, volume, and microstructure. A
        # futures bot that evaluates entries on SPOT candles gets stale/mismatched
        # prices (futures trade at a different mark), so ATR/breakout/volume
        # signals computed on spot candles misfire. Pick the endpoint for the
        # market the bot is actually trading.
        if market == "futures":
            path = "/futures-usdt/candlesticks"
            params = {"contract": symbol, "interval": interval, "limit": limit}
        else:
            path = "/spot/candlesticks"
            params = {"currency_pair": symbol, "interval": interval, "limit": limit}
        data = await self.request("GET", path, params=params)
        candles = self._parse_candles(data)
        # Entry/indicator evaluation must run on CLOSED bars only — the last bar
        # Gate.io returns is the still-forming one, which repaints (RSI/volume/EMA
        # flicker intrabar) and makes the volume filter reject on a partial bar.
        # Position management keeps it (drop_unclosed=False) for price freshness.
        if drop_unclosed:
            candles = [c for c in candles if c.get("closed", True)]
        return candles

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
            # Index 7 is Gate.io's window_close flag (true once the bar is final).
            # Absent on older responses -> assume closed for backward compatibility.
            closed = True
            if len(item) > 7 and item[7] not in (None, ""):
                closed = str(item[7]).lower() == "true"
            result.append(
                {
                    "timestamp": item[0],
                    "volume": base_volume,
                    "quote_volume": quote_volume,
                    "close": close,
                    "high": Decimal(str(item[3])),
                    "low": Decimal(str(item[4])),
                    "open": Decimal(str(item[5])),
                    "closed": closed,
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
        info = await self.request("GET", f"/spot/currency_pairs/{symbol}")
        if info:
            self._pair_cache[symbol] = (info, time.monotonic())
            return info
        # API failure: return stale cache if available, else empty dict.
        return cached[0] if cached else {}

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

    async def _submit_spot_limit(
        self, symbol: str, side: str, amount: Decimal, price: Decimal,
        post_only: bool = True, time_in_force: str = "gtc",
    ) -> dict:
        """Submit a spot LIMIT order. ``post_only`` (IOC-rejecting maker) is the
        default so the order rests as a maker and never crosses the book (no
        taker fee). Used by the adaptive/limit entry path to capture the maker
        rebate instead of paying market slippage."""
        body = {
            "currency_pair": symbol,
            "type": "limit",
            "side": side,
            "amount": str(amount),
            "price": str(price),
            "account": "spot",
            "time_in_force": time_in_force,
        }
        if post_only:
            body["post_only"] = True
        return await self.request("POST", "/spot/orders", json_body=body)

    async def place_limit_buy(self, symbol: str, quote_amount: Decimal, price: Decimal) -> dict:
        """Limit BUY (maker). `quote_amount` is the USDT to spend; converted to
        base currency internally (Gate.io limit orders expect ``amount`` in base),
        rounded to ``amount_precision`` and checked against ``min_base_amount``."""
        if price <= 0:
            raise OrderBelowMinimum(f"{symbol} limit buy price must be positive")
        info = await self.currency_pair_info(symbol)
        base_amount = quote_amount / price
        amount = self._round_down(base_amount, int(info.get("amount_precision", 8) or 8))
        min_base = Decimal(str(info.get("min_base_amount", "0") or "0"))
        if amount <= 0 or amount < min_base:
            raise OrderBelowMinimum(
                f"{symbol} limit buy base {amount} below minimum {min_base}"
            )
        return await self._submit_spot_limit(symbol, "buy", amount, price)

    async def place_limit_sell(self, symbol: str, base_amount: Decimal, price: Decimal) -> dict:
        """Limit SELL (maker). `base_amount` is the BASE quantity, rounded to
        amount_precision and checked against min_base_amount."""
        info = await self.currency_pair_info(symbol)
        amount = self._round_down(base_amount, int(info.get("amount_precision", 8) or 8))
        min_base = Decimal(str(info.get("min_base_amount", "0") or "0"))
        if amount <= 0 or amount < min_base:
            raise OrderBelowMinimum(
                f"{symbol} limit sell base {amount} below minimum {min_base}"
            )
        return await self._submit_spot_limit(symbol, "sell", amount, price)

    async def cancel_spot_order(self, symbol: str, order_id: str) -> None:
        """Cancel a spot order. Best-effort: a 404 (already filled/cancelled) is
        swallowed since the desired end state is reached."""
        try:
            await self.request(
                "DELETE", f"/spot/orders/{order_id}", params={"currency_pair": symbol}
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    async def get_order_status(self, symbol: str, order_id: str) -> dict:
        """Fetch a spot order's current status (for adaptive limit fill checks)."""
        return await self.request(
            "GET", f"/spot/orders/{order_id}", params={"currency_pair": symbol}
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

    # ------------------------------------------------------------------
    # USDT-perpetual futures (opt-in via trading_market="futures").
    #
    # NOTE: these endpoints place REAL leveraged orders and are NOT exercised in
    # CI (no exchange in the test env). Validate on Gate.io's futures testnet
    # before enabling live. Sizes are in CONTRACTS; one contract equals the
    # contract's quanto_multiplier units of the base asset.
    # ------------------------------------------------------------------

    @property
    def _settle(self) -> str:
        return get_settings().futures_settle.lower()

    async def futures_contract_info(self, contract: str) -> dict:
        """Cached futures contract metadata (quanto_multiplier, order_size_min)."""
        key = f"fut:{contract}"
        cached = self._pair_cache.get(key)
        if cached is not None:
            info, ts = cached
            if time.monotonic() - ts < self._pair_cache_ttl:
                return info
        info = await self.request("GET", f"/futures/{self._settle}/contracts/{contract}")
        if info:
            self._pair_cache[key] = (info, time.monotonic())
            return info
        return cached[0] if cached else {}

    async def futures_last_price(self, contract: str) -> Decimal | None:
        data = await self.request(
            "GET", f"/futures/{self._settle}/tickers", params={"contract": contract}
        )
        if not data:
            return None
        last = data[0].get("last")
        return Decimal(str(last)) if last not in (None, "", "0") else None

    async def set_futures_leverage(self, contract: str, leverage: int) -> dict:
        """Set isolated-margin leverage for a contract (no-op-safe to call again)."""
        return await self.request(
            "POST",
            f"/futures/{self._settle}/positions/{contract}/leverage",
            params={"leverage": str(int(leverage))},
        )

    def _contracts_for_base(self, base_quantity: Decimal, info: dict) -> int:
        """Convert a base-asset quantity to an INTEGER number of contracts,
        rounding DOWN so we never exceed the intended size."""
        mult = Decimal(str(info.get("quanto_multiplier", "0") or "0"))
        if mult <= 0:
            return 0
        return int((base_quantity / mult).to_integral_value(rounding=ROUND_DOWN))

    async def place_futures_market_order(
        self, contract: str, base_quantity: Decimal, direction: str, reduce_only: bool = False
    ) -> dict:
        """Market order on USDT-perpetual futures.

        ``direction`` is "long"/"short" for opens; for a reduce-only close pass the
        direction of the CLOSING trade (opposite the position). Size is signed:
        positive opens/adds long, negative opens/adds short. A market order is a
        price="0" IOC order on Gate.io futures.
        """
        info = await self.futures_contract_info(contract)
        size = self._contracts_for_base(abs(base_quantity), info)
        order_size_min = int(info.get("order_size_min", 1) or 1)
        if size < order_size_min:
            raise OrderBelowMinimum(
                f"{contract} futures size {size} contracts below minimum {order_size_min}"
            )
        signed = -size if direction == "short" else size
        body = {
            "contract": contract,
            "size": signed,
            "price": "0",
            "tif": "ioc",
            "reduce_only": reduce_only,
        }
        return await self.request("POST", f"/futures/{self._settle}/orders", json_body=body)

    async def place_futures_limit_order(
        self, contract: str, base_quantity: Decimal, direction: str,
        price: Decimal, reduce_only: bool = False, post_only: bool = True,
    ) -> dict:
        """Limit order on USDT-perpetual futures (maker). ``post_only`` rejects
        the order if it would cross the book, guaranteeing a maker fill (no
        taker fee). Used by the adaptive/limit entry path to capture the maker
        rebate on futures. Size is signed (negative = short)."""
        info = await self.futures_contract_info(contract)
        size = self._contracts_for_base(abs(base_quantity), info)
        order_size_min = int(info.get("order_size_min", 1) or 1)
        if size < order_size_min:
            raise OrderBelowMinimum(
                f"{contract} futures limit size {size} contracts below minimum {order_size_min}"
            )
        signed = -size if direction == "short" else size
        body = {
            "contract": contract,
            "size": signed,
            "price": str(price),
            "tif": "gtc",
            "reduce_only": reduce_only,
            "post_only": post_only,
        }
        return await self.request("POST", f"/futures/{self._settle}/orders", json_body=body)

    async def cancel_futures_order(self, contract: str, order_id: str) -> None:
        """Cancel a futures order. Best-effort: a 404 is swallowed."""
        try:
            await self.request(
                "DELETE", f"/futures/{self._settle}/orders/{order_id}",
                params={"contract": contract},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    async def get_futures_order_status(self, contract: str, order_id: str) -> dict:
        """Fetch a futures order's current status (for adaptive limit fill checks)."""
        return await self.request(
            "GET", f"/futures/{self._settle}/orders/{order_id}",
            params={"contract": contract},
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

    # ------------------------------------------------------------------
    # Exchange-side stop orders (capital preservation).
    #
    # A stop resting on the exchange protects the position even when the
    # scheduler is stuck/crashed or a fast adverse move gaps through the
    # 15-min polling cadence. The local poll in TradingEngine remains as a
    # secondary safety net and to drive trailing/breakeven amendments.
    #
    # Gate.io exposes two distinct mechanisms:
    #   - Spot: price-triggered conditional orders (`/spot/price_orders`) that
    #     fire a market order when the trigger price is crossed.
    #   - Futures: close-only conditional orders (`/futures/{settle}/conditional_orders`)
    #     that close the position when the mark/last price crosses the trigger.
    # ------------------------------------------------------------------

    async def place_spot_stop_loss(
        self, symbol: str, stop_price: Decimal, base_amount: Decimal, is_short: bool
    ) -> dict:
        """Place a spot price-triggered stop-loss that rests on the exchange.

        For a LONG the stop fires when price falls to ``stop_price`` (rule "<=")
        and sells ``base_amount`` of the base asset. For a SHORT on spot (which
        cannot exist — shorts are futures-only) the rule would invert, but this
        path is only reached for longs since ``_execute_entry`` skips shorts on
        spot. We keep the ``is_short`` flag for symmetry and future proofing.
        """
        info = await self.currency_pair_info(symbol)
        amount = self._round_down(base_amount, int(info.get("amount_precision", 8) or 8))
        min_base = Decimal(str(info.get("min_base_amount", "0") or "0"))
        if amount <= 0 or amount < min_base:
            raise OrderBelowMinimum(
                f"{symbol} stop-loss sell base {amount} below minimum {min_base}"
            )
        # Long stop: price <= trigger -> sell. Short would be price >= trigger -> buy.
        rule = ">=" if is_short else "<="
        side = "buy" if is_short else "sell"
        body = {
            "trigger": {"price": str(stop_price), "rule": rule},
            "put": {
                "type": "market",
                "side": side,
                "price": "0",
                "amount": str(amount),
                "account": "spot",
                "time_in_force": "ioc",
            },
            "market": {"currency_pair": symbol},
        }
        return await self.request("POST", "/spot/price_orders", json_body=body)

    async def cancel_spot_price_order(self, order_id: str) -> None:
        """Cancel a spot price-triggered order. Best-effort: a 404 (already
        triggered/cancelled) is swallowed since the desired end state is reached."""
        try:
            await self.request("DELETE", f"/spot/price_orders/{order_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    async def place_futures_stop_loss(
        self, contract: str, stop_price: Decimal, is_short: bool
    ) -> dict:
        """Place a futures close-only conditional stop-loss order.

        ``close=true`` instructs Gate.io to close the entire position when the
        trigger fires, so no size is required. A LONG stop fires when the price
        falls to ``stop_price`` (rule "<="); a SHORT stop fires when the price
        rises to it (rule ">=").
        """
        rule = ">=" if is_short else "<="
        body = {
            "contract": contract,
            "close": True,
            "price": str(stop_price),
            "rule": rule,
            "reduce_only": True,
            "size": 0,
        }
        return await self.request(
            "POST", f"/futures/{self._settle}/conditional_orders", json_body=body
        )

    async def cancel_futures_conditional_order(self, order_id: str) -> None:
        """Cancel a futures conditional order. Best-effort: a 404 is swallowed."""
        try:
            await self.request(
                "DELETE", f"/futures/{self._settle}/conditional_orders/{order_id}"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    async def get_futures_position(self, contract: str) -> dict | None:
        """Fetch the live futures position for ``contract``.

        Returns the raw Gate.io position object (with ``liquidation_price``,
        ``entry_price``, ``size``, ``leverage``, ``margin``, ...) or None when
        no position is open on that contract. Used for liquidation-distance
        monitoring and leverage read-back verification.
        """
        data = await self.request(
            "GET", f"/futures/{self._settle}/positions/{contract}"
        )
        if not data:
            return None
        # Gate.io returns a single position object (or an empty body when flat).
        return data if isinstance(data, dict) else (data[0] if data else None)

    async def get_futures_funding_rate(self, contract: str) -> dict | None:
        """Fetch the current funding rate for a USDT-perp contract.

        Returns the raw Gate.io funding object (with ``r`` as the funding rate
        fraction, ``next_funding_time`` as a unix timestamp) or None on failure.
        Used by the funding-signal regime input: a strongly positive funding
        rate is a headwind for longs (they pay shorts) and a tailwind for
        shorts; a strongly negative rate is the mirror. Extreme funding is a
        contrarian/mean-reversion signal (crowded positioning).
        """
        try:
            data = await self.request(
                "GET", f"/futures/{self._settle}/funding_rate",
                params={"contract": contract},
            )
            return data if isinstance(data, dict) else (data[0] if data else None)
        except Exception:
            return None

    async def get_order_book(self, symbol: str, depth: int = 20, market: str = "spot") -> dict | None:
        """Fetch the order book snapshot (best N bids/asks).

        Returns ``{"bids": [[price, amount], ...], "asks": [[price, amount], ...]}``
        or None on failure.  Supports both spot and futures (futures uses the
        ``/futures/{settle}/order_book`` endpoint with ``contract`` param).
        """
        try:
            if market == "futures":
                data = await self.request(
                    "GET", f"/futures/{self._settle}/order_book",
                    params={"contract": symbol, "limit": int(depth)},
                )
            else:
                data = await self.request(
                    "GET", "/spot/order_book",
                    params={"currency_pair": symbol, "limit": int(depth)},
                )
            return data
        except Exception:
            return None
