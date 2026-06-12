"""Tests for Gate.io order semantics: buy(quote)/sell(base), precision, minimums."""
from decimal import Decimal

import pytest

from app.services.exchange.gateio import GateIOClient, OrderBelowMinimum
from app.services.trading_engine import _fee_in_quote


@pytest.fixture
def client(monkeypatch):
    c = GateIOClient()
    pair = {
        "precision": 2,          # quote (price) precision
        "amount_precision": 4,   # base amount precision
        "min_quote_amount": "5",
        "min_base_amount": "0.001",
    }

    async def fake_pair(symbol):
        return pair

    captured = {}

    async def fake_submit(symbol, side, amount):
        captured["symbol"] = symbol
        captured["side"] = side
        captured["amount"] = amount
        return {"id": "1", "status": "closed"}

    monkeypatch.setattr(c, "currency_pair_info", fake_pair)
    monkeypatch.setattr(c, "_submit_market", fake_submit)
    c._captured = captured
    return c


async def test_market_buy_uses_quote_amount_rounded(client):
    # Quote spend rounded DOWN to 2 dp; side buy.
    await client.place_market_buy("BTC_USDT", Decimal("100.12999"))
    assert client._captured["side"] == "buy"
    assert client._captured["amount"] == Decimal("100.12")


async def test_market_buy_below_min_quote_raises(client):
    with pytest.raises(OrderBelowMinimum):
        await client.place_market_buy("BTC_USDT", Decimal("4.99"))


async def test_market_sell_uses_base_amount_rounded(client):
    await client.place_market_sell("BTC_USDT", Decimal("0.0123456"))
    assert client._captured["side"] == "sell"
    assert client._captured["amount"] == Decimal("0.0123")  # 4 dp, round down


async def test_market_sell_below_min_base_raises(client):
    with pytest.raises(OrderBelowMinimum):
        await client.place_market_sell("BTC_USDT", Decimal("0.0009"))


async def test_submit_market_sets_ioc_time_in_force(monkeypatch):
    c = GateIOClient()
    sent = {}

    async def fake_request(method, path, *, params=None, json_body=None):
        sent["body"] = json_body
        return {"id": "1"}

    monkeypatch.setattr(c, "request", fake_request)
    await c._submit_market("BTC_USDT", "buy", Decimal("10"))
    assert sent["body"]["time_in_force"] == "ioc"
    assert sent["body"]["type"] == "market"


def test_fee_in_quote_converts_base_fee():
    # Buy fee paid in BTC (base) must be converted to quote at the fill price.
    resp = {"fee": "0.001", "fee_currency": "BTC"}
    assert _fee_in_quote(resp, Decimal("50000"), "BTC_USDT") == Decimal("50.000")


def test_fee_in_quote_passes_through_quote_fee():
    resp = {"fee": "2.5", "fee_currency": "USDT"}
    assert _fee_in_quote(resp, Decimal("50000"), "BTC_USDT") == Decimal("2.5")


async def test_candles_expose_base_and_quote_volume(monkeypatch):
    c = GateIOClient()
    raw = [
        # 6-element (no base volume): quote=1000, close=100 -> base 10
        [1700000000, "1000", "100", "101", "99", "100"],
        # 8-element: base volume present at index 6 -> used directly
        [1700003600, "2000", "200", "201", "199", "200", "8", True],
    ]

    async def fake_request(method, path, *, params=None, json_body=None):
        return raw

    monkeypatch.setattr(c, "request", fake_request)
    candles = await c.candles("BTC_USDT")
    by_ts = {x["timestamp"]: x for x in candles}
    assert by_ts[1700000000]["volume"] == Decimal("10")        # derived quote/close
    assert by_ts[1700000000]["quote_volume"] == Decimal("1000")
    assert by_ts[1700003600]["volume"] == Decimal("8")         # from base-volume field


async def test_last_price_falls_back_to_bid_ask_mid(monkeypatch):
    c = GateIOClient()

    async def fake_ticker(symbol):
        return {"last": None, "highest_bid": "100", "lowest_ask": "102"}

    monkeypatch.setattr(c, "ticker", fake_ticker)
    assert await c.last_price("BTC_USDT") == Decimal("101")


async def test_request_honors_retry_after_on_429(monkeypatch):
    import httpx as _httpx

    from app.services.exchange import gateio as gateio_mod

    c = GateIOClient()
    delays = []

    async def fake_sleep(d):
        delays.append(d)

    def make_429(*args, **kwargs):
        request = _httpx.Request("GET", "https://example/x")
        response = _httpx.Response(429, headers={"Retry-After": "30"}, request=request)
        raise _httpx.HTTPStatusError("rate limited", request=request, response=response)

    async def fake_request(*args, **kwargs):
        make_429()

    monkeypatch.setattr(gateio_mod.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(c.client, "request", fake_request)
    with pytest.raises(_httpx.HTTPStatusError):
        await c.request("GET", "/spot/accounts")
    # Backoff must respect the server's Retry-After (30s), not the 2/4s guess.
    assert any(d == 30 for d in delays)


def test_strategy_thresholds_loaded_from_config():
    from app.services.strategy.signals import CapitalPreservationStrategy

    strat = CapitalPreservationStrategy()
    assert float(strat.rsi_threshold) == 45.0
    assert float(strat.max_24h_range_pct) == 0.12
