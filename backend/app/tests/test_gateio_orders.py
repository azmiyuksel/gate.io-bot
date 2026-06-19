"""Tests for Gate.io order semantics: buy(quote)/sell(base), precision, minimums."""
from decimal import Decimal, ROUND_DOWN

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
    assert float(strat.rsi_threshold) == 35.0
    assert float(strat.max_24h_range_pct) == 0.12


# --- Fill accounting fixes: filled_total is QUOTE, base fee handling ---


def test_filled_base_qty_derives_base_from_quote_filled_total():
    from app.services.trading_engine import _filled_base_qty

    # filled_total (2000 USDT) is quote-denominated; at price 200 -> 10 base.
    resp = {"filled_total": "2000", "amount": "0", "left": "0"}
    assert _filled_base_qty(resp, Decimal("200"), Decimal("0")) == Decimal("10")


def test_filled_base_qty_falls_back_to_amount_minus_left():
    from app.services.trading_engine import _filled_base_qty

    # No filled_total -> use base amount minus the unfilled remainder (sell semantics).
    resp = {"filled_total": "0", "amount": "5", "left": "1"}
    assert _filled_base_qty(resp, Decimal("0"), Decimal("99")) == Decimal("4")


def test_filled_base_qty_uses_fallback_when_no_data():
    from app.services.trading_engine import _filled_base_qty

    assert _filled_base_qty({}, Decimal("0"), Decimal("7")) == Decimal("7")


def test_fee_in_base_returns_base_fee_only():
    from app.services.trading_engine import _fee_in_base

    assert _fee_in_base({"fee": "0.001", "fee_currency": "BTC"}, "BTC_USDT") == Decimal("0.001")
    assert _fee_in_base({"fee": "2.5", "fee_currency": "USDT"}, "BTC_USDT") == Decimal("0")


def test_trend_filter_blocks_entries_below_ema200():
    from app.services.strategy.signals import CapitalPreservationStrategy

    # Steady downtrend: last close sits well below the 200 EMA.
    # Long entries blocked, short entries only if RSI is overbought.
    candles = []
    for i in range(400):
        price = Decimal("200") - Decimal(str(i)) * Decimal("0.25")
        candles.append({
            "timestamp": 1700000000 + i * 3600,
            "open": price, "high": price + 1, "low": price - 1, "close": price,
            "volume": Decimal("1000"), "quote_volume": price * Decimal("1000"),
        })

    strat = CapitalPreservationStrategy()
    assert strat.trend_filter_enabled is True
    signal = strat.evaluate(candles)
    assert signal.should_enter is False
    # In a downtrend, long entries are blocked; checks short conditions instead
    assert signal.reason == "rsi_not_overbought"


def _cp_settings():
    """Settings selecting the capital-preservation paper strategy (the default is
    now the frequent momentum strategy)."""
    from app.core.config import Settings

    return Settings(
        environment="local", secret_key="t", fernet_key="t",
        paper_strategy="capital_preservation_v1",
    )


def test_paper_adapter_uses_looser_paper_thresholds():
    # When capital_preservation_v1 is selected, paper runs DELIBERATELY looser than
    # live so the simulation generates enough activity to observe.
    from decimal import Decimal
    from unittest.mock import patch

    from app.paper_trading.strategy_adapter import CapitalPreservationAdapter
    from app.services.strategy.signals import CapitalPreservationStrategy

    live = CapitalPreservationStrategy()
    with patch("app.paper_trading.strategy_adapter.get_settings", return_value=_cp_settings()):
        paper = CapitalPreservationAdapter()._strategy
    assert paper.trend_filter_enabled is True
    assert paper.rsi_threshold == Decimal("45")
    assert paper.ema20_distance_pct == Decimal("0.03")
    assert paper.trend_tolerance_pct == Decimal("0.02")
    # Paper must be looser than live, not stricter.
    assert paper.rsi_threshold > live.rsi_threshold
    assert paper.ema20_distance_pct > live.ema20_distance_pct
    assert paper.trend_tolerance_pct > live.trend_tolerance_pct
    assert live.trend_tolerance_pct == Decimal("0")  # live stays strict


def test_paper_trend_tolerance_allows_long_just_below_ema200():
    """A long setup ~1.3% below the (laggy) EMA200 with an oversold RSI:
    live stays out (strict trend gate), but paper's 2% tolerance enters — this is
    the lever that keeps the simulation active in neutral/mildly-down chop."""
    from decimal import Decimal
    from unittest.mock import patch

    from app.paper_trading.strategy_adapter import CapitalPreservationAdapter
    from app.services.strategy.signals import CapitalPreservationStrategy

    # 380 flat bars at 100, then a gentle 20-bar decline so the last close sits
    # ~1.3% below EMA200 (inside paper's 2% band, outside live's strict 0%).
    candles = []
    base = Decimal("100")
    for i in range(380):
        candles.append({
            "timestamp": 1700000000 + i * 900,
            "open": base, "high": base + Decimal("0.2"), "low": base - Decimal("0.2"),
            "close": base, "volume": Decimal("1000"), "quote_volume": base * 1000,
        })
    price = base
    for i in range(20):
        price = price - Decimal("0.07")
        candles.append({
            "timestamp": 1700000000 + (380 + i) * 900,
            "open": price + Decimal("0.07"), "high": price + Decimal("0.2"),
            "low": price - Decimal("0.2"), "close": price,
            "volume": Decimal("1000"), "quote_volume": price * 1000,
        })

    live = CapitalPreservationStrategy().evaluate(candles)
    with patch("app.paper_trading.strategy_adapter.get_settings", return_value=_cp_settings()):
        paper_strat = CapitalPreservationAdapter()._strategy
    paper = paper_strat.evaluate(candles)
    assert live.should_enter is False  # strict gate blocks a long below EMA200
    assert paper.should_enter is True and paper.direction == "long"


async def test_candles_range_pages_past_1000_cap(monkeypatch):
    from datetime import UTC, datetime

    c = GateIOClient()
    pages = [
        [[t, "100", "10", "11", "9", "10"] for t in range(200, 210)],  # newest page
        [[t, "100", "10", "11", "9", "10"] for t in range(190, 200)],  # older page
        [],
    ]
    calls = {"i": 0}

    async def fake_request(method, path, *, params=None, json_body=None):
        i = calls["i"]
        calls["i"] += 1
        return pages[i] if i < len(pages) else []

    monkeypatch.setattr(c, "request", fake_request)
    start = datetime.fromtimestamp(195, tz=UTC)
    end = datetime.fromtimestamp(10_000, tz=UTC)
    out = await c.candles_range("BTC_USDT", "1h", start, end)
    ts = [int(x["timestamp"]) for x in out]
    assert ts == sorted(ts)                 # ascending
    assert ts[0] == 195 and ts[-1] == 209   # filtered to [start, end]
    assert len(ts) == 15                     # 195..209, de-duplicated across pages


def test_symbols_property_normalizes_and_dedupes():
    from app.core.config import Settings

    s = Settings(
        secret_key="t", fernet_key="t",
        trading_symbols="btc_usdt, ETH_USDT ,btc_usdt,, sol_usdt",
    )
    assert s.symbols == ["BTC_USDT", "ETH_USDT", "SOL_USDT"]


# --- Exchange-side stop orders (capital preservation) ---


async def test_place_spot_stop_loss_long_sells_on_price_drop(monkeypatch):
    """A LONG spot stop fires when price <= trigger and sells the base amount."""
    c = GateIOClient()
    sent = {}

    async def fake_pair(symbol):
        return {"amount_precision": 4, "min_base_amount": "0.001"}

    async def fake_request(method, path, *, params=None, json_body=None):
        sent["method"] = method
        sent["path"] = path
        sent["body"] = json_body
        return {"id": "stop-1"}

    monkeypatch.setattr(c, "currency_pair_info", fake_pair)
    monkeypatch.setattr(c, "request", fake_request)
    resp = await c.place_spot_stop_loss("BTC_USDT", Decimal("49000"), Decimal("0.5"), is_short=False)
    assert resp["id"] == "stop-1"
    # Long stop: trigger rule "<=" (price falls to stop), put side "sell".
    assert sent["body"]["trigger"]["rule"] == "<="
    assert sent["body"]["trigger"]["price"] == "49000"
    assert sent["body"]["put"]["side"] == "sell"
    assert sent["body"]["put"]["type"] == "market"
    assert Decimal(str(sent["body"]["put"]["amount"])) == Decimal("0.5")
    assert sent["body"]["market"]["currency_pair"] == "BTC_USDT"
    assert sent["path"] == "/spot/price_orders"


async def test_place_spot_stop_loss_short_inverts_rule_and_side(monkeypatch):
    c = GateIOClient()
    sent = {}

    async def fake_pair(symbol):
        return {"amount_precision": 4, "min_base_amount": "0.001"}

    async def fake_request(method, path, *, params=None, json_body=None):
        sent["body"] = json_body
        return {"id": "stop-2"}

    monkeypatch.setattr(c, "currency_pair_info", fake_pair)
    monkeypatch.setattr(c, "request", fake_request)
    await c.place_spot_stop_loss("BTC_USDT", Decimal("51000"), Decimal("0.5"), is_short=True)
    # Short stop: trigger rule ">=" (price rises to stop), put side "buy".
    assert sent["body"]["trigger"]["rule"] == ">="
    assert sent["body"]["put"]["side"] == "buy"


async def test_place_spot_stop_loss_below_min_raises(monkeypatch):
    c = GateIOClient()

    async def fake_pair(symbol):
        return {"amount_precision": 4, "min_base_amount": "0.001"}

    monkeypatch.setattr(c, "currency_pair_info", fake_pair)
    with pytest.raises(OrderBelowMinimum):
        await c.place_spot_stop_loss("BTC_USDT", Decimal("49000"), Decimal("0.0005"), is_short=False)


async def test_place_futures_stop_loss_long_closes_position_on_drop(monkeypatch):
    """A LONG futures stop is a close-only conditional order firing on price <= trigger."""
    c = GateIOClient()
    sent = {}

    async def fake_request(method, path, *, params=None, json_body=None):
        sent["method"] = method
        sent["path"] = path
        sent["body"] = json_body
        return {"id": "fut-stop-1"}

    monkeypatch.setattr(c, "request", fake_request)
    resp = await c.place_futures_stop_loss("BTC_USDT", Decimal("49000"), is_short=False)
    assert resp["id"] == "fut-stop-1"
    assert sent["body"]["close"] is True
    assert sent["body"]["reduce_only"] is True
    assert sent["body"]["rule"] == "<="
    assert sent["body"]["price"] == "49000"
    assert sent["body"]["contract"] == "BTC_USDT"
    assert sent["body"]["size"] == 0
    assert "/conditional_orders" in sent["path"]


async def test_place_futures_stop_loss_short_uses_ge_rule(monkeypatch):
    c = GateIOClient()
    sent = {}

    async def fake_request(method, path, *, params=None, json_body=None):
        sent["body"] = json_body
        return {"id": "fut-stop-2"}

    monkeypatch.setattr(c, "request", fake_request)
    await c.place_futures_stop_loss("BTC_USDT", Decimal("51000"), is_short=True)
    # Short stop: price rises to stop -> rule ">=".
    assert sent["body"]["rule"] == ">="


async def test_cancel_spot_price_order_swallows_404(monkeypatch):
    """A 404 (already triggered/cancelled) is swallowed — desired end state reached."""
    import httpx as _httpx

    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        request = _httpx.Request("DELETE", "https://example/x")
        raise _httpx.HTTPStatusError(
            "not found", request=request,
            response=_httpx.Response(404, request=request),
        )

    monkeypatch.setattr(c, "request", fake_request)
    # Should not raise.
    await c.cancel_spot_price_order("123")


async def test_cancel_futures_conditional_order_swallows_404(monkeypatch):
    import httpx as _httpx

    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        request = _httpx.Request("DELETE", "https://example/x")
        raise _httpx.HTTPStatusError(
            "not found", request=request,
            response=_httpx.Response(404, request=request),
        )

    monkeypatch.setattr(c, "request", fake_request)
    await c.cancel_futures_conditional_order("456")


async def test_cancel_spot_price_order_propagates_non_404(monkeypatch):
    """A 500 on cancel must propagate (the stop may still be resting)."""
    import httpx as _httpx

    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        request = _httpx.Request("DELETE", "https://example/x")
        raise _httpx.HTTPStatusError(
            "server error", request=request,
            response=_httpx.Response(500, request=request),
        )

    monkeypatch.setattr(c, "request", fake_request)
    with pytest.raises(_httpx.HTTPStatusError):
        await c.cancel_spot_price_order("123")


async def test_get_futures_position_returns_position_dict(monkeypatch):
    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        return {"contract": "BTC_USDT", "size": 10, "liquidation_price": "40000", "leverage": 5}

    monkeypatch.setattr(c, "request", fake_request)
    pos = await c.get_futures_position("BTC_USDT")
    assert pos is not None
    assert pos["liquidation_price"] == "40000"
    assert pos["leverage"] == 5


async def test_get_futures_position_returns_none_when_flat(monkeypatch):
    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        return None

    monkeypatch.setattr(c, "request", fake_request)
    assert await c.get_futures_position("BTC_USDT") is None


# --- Maker limit orders (capture the rebate instead of paying taker) ---


async def test_place_limit_buy_posts_passive_maker(monkeypatch):
    """A limit BUY posts at the given price as a post-only maker order."""
    c = GateIOClient()
    sent = {}

    async def fake_pair(symbol):
        return {"amount_precision": 8, "min_base_amount": "0.0001"}

    async def fake_request(method, path, *, params=None, json_body=None):
        sent["body"] = json_body
        sent["path"] = path
        return {"id": "lim-1"}

    monkeypatch.setattr(c, "currency_pair_info", fake_pair)
    monkeypatch.setattr(c, "request", fake_request)
    # quote_amount=100.12, price=49000 → base = 100.12/49000, rounded DOWN to 8 decimals
    await c.place_limit_buy("BTC_USDT", Decimal("100.12"), Decimal("49000"))
    assert sent["body"]["type"] == "limit"
    assert sent["body"]["side"] == "buy"
    assert sent["body"]["price"] == "49000"
    expected_base = (Decimal("100.12") / Decimal("49000")).quantize(
        Decimal("0.00000001"), rounding=ROUND_DOWN
    )
    assert Decimal(str(sent["body"]["amount"])) == expected_base
    assert sent["body"]["post_only"] is True
    assert sent["body"]["time_in_force"] == "gtc"


async def test_place_limit_sell_uses_base_amount(monkeypatch):
    c = GateIOClient()
    sent = {}

    async def fake_pair(symbol):
        return {"amount_precision": 4, "min_base_amount": "0.001"}

    async def fake_request(method, path, *, params=None, json_body=None):
        sent["body"] = json_body
        return {"id": "lim-2"}

    monkeypatch.setattr(c, "currency_pair_info", fake_pair)
    monkeypatch.setattr(c, "request", fake_request)
    await c.place_limit_sell("BTC_USDT", Decimal("0.5"), Decimal("51000"))
    assert sent["body"]["side"] == "sell"
    assert Decimal(str(sent["body"]["amount"])) == Decimal("0.5")
    assert sent["body"]["price"] == "51000"
    assert sent["body"]["post_only"] is True


async def test_place_limit_buy_below_min_raises(monkeypatch):
    c = GateIOClient()

    async def fake_pair(symbol):
        return {"amount_precision": 8, "min_base_amount": "0.01"}

    monkeypatch.setattr(c, "currency_pair_info", fake_pair)
    # quote_amount=4, price=49000 → base = 4/49000 ≈ 0.0000816 < min_base_amount 0.01
    with pytest.raises(OrderBelowMinimum):
        await c.place_limit_buy("BTC_USDT", Decimal("4"), Decimal("49000"))


async def test_place_futures_limit_order_signs_size_for_short(monkeypatch):
    """A futures limit SHORT signs the size negative and posts as a maker."""
    c = GateIOClient()

    async def fake_contract(contract):
        return {"quanto_multiplier": "0.0001", "order_size_min": "1"}

    sent = {}

    async def fake_request(method, path, *, params=None, json_body=None):
        sent["body"] = json_body
        sent["path"] = path
        return {"id": "fut-lim-1"}

    monkeypatch.setattr(c, "futures_contract_info", fake_contract)
    monkeypatch.setattr(c, "request", fake_request)
    await c.place_futures_limit_order("BTC_USDT", Decimal("1"), "short", Decimal("51000"))
    # 1 / 0.0001 = 10000 contracts, NEGATIVE for a short.
    assert sent["body"]["size"] == -10000
    assert sent["body"]["price"] == "51000"
    assert sent["body"]["tif"] == "gtc"
    assert sent["body"]["post_only"] is True
    assert sent["body"]["reduce_only"] is False


async def test_cancel_spot_order_swallows_404(monkeypatch):
    import httpx as _httpx

    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        request = _httpx.Request("DELETE", "https://example/x")
        raise _httpx.HTTPStatusError(
            "not found", request=request,
            response=_httpx.Response(404, request=request),
        )

    monkeypatch.setattr(c, "request", fake_request)
    await c.cancel_spot_order("BTC_USDT", "123")  # no raise


async def test_cancel_futures_order_swallows_404(monkeypatch):
    import httpx as _httpx

    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        request = _httpx.Request("DELETE", "https://example/x")
        raise _httpx.HTTPStatusError(
            "not found", request=request,
            response=_httpx.Response(404, request=request),
        )

    monkeypatch.setattr(c, "request", fake_request)
    await c.cancel_futures_order("BTC_USDT", "456")  # no raise


async def test_get_order_status_returns_current_state(monkeypatch):
    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        return {"id": "123", "status": "closed", "filled_total": "500"}

    monkeypatch.setattr(c, "request", fake_request)
    status = await c.get_order_status("BTC_USDT", "123")
    assert status["status"] == "closed"
    assert status["filled_total"] == "500"


# --- Funding rate signal (futures microstructure input) ---


async def test_get_futures_funding_rate_returns_rate(monkeypatch):
    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        return {"r": "0.0008", "next_funding_time": "1700000000"}

    monkeypatch.setattr(c, "request", fake_request)
    funding = await c.get_futures_funding_rate("BTC_USDT")
    assert funding is not None
    assert funding["r"] == "0.0008"


async def test_get_futures_funding_rate_returns_none_on_failure(monkeypatch):
    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(c, "request", fake_request)
    # Best-effort: a fetch failure returns None (advisory, never blocks an entry).
    assert await c.get_futures_funding_rate("BTC_USDT") is None


async def test_funding_signal_de_risks_adverse_long(db_session, monkeypatch):
    """A positive funding rate above the threshold is a headwind for a LONG
    (it pays shorts while held) -> size is de-risked by funding_signal_risk_mult."""
    from unittest.mock import AsyncMock

    from app.core.config import get_settings
    from app.models.entities import StrategySettings
    from app.services.strategy.signals import Signal
    from app.services.trading_engine import TradingEngine

    settings = get_settings()
    monkeypatch.setattr(settings, "trading_market", "futures", raising=False)
    monkeypatch.setattr(settings, "funding_signal_enabled", True, raising=False)
    monkeypatch.setattr(settings, "funding_signal_threshold_pct", 0.0005, raising=False)
    monkeypatch.setattr(settings, "funding_signal_risk_mult", 0.5, raising=False)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    row.atr_multiplier = Decimal("2")
    row.min_reward_risk = Decimal("1.5")
    row.max_capital_per_trade_pct = Decimal("0.05")
    db_session.commit()

    client = AsyncMock()
    client.get_futures_funding_rate = AsyncMock(return_value={"r": "0.0008"})  # adverse for long
    engine = TradingEngine(db_session, client)
    engine.notifier = AsyncMock()
    sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
    mult = await engine._check_funding_signal("BTC_USDT", sig)
    assert mult == Decimal("0.5")


async def test_funding_signal_does_not_boost_favorable_long(db_session, monkeypatch):
    """A NEGATIVE funding rate is favorable for a long (shorts pay longs) — but
    the signal is asymmetric (protect capital first): it does NOT boost size."""
    from unittest.mock import AsyncMock

    from app.core.config import get_settings
    from app.models.entities import StrategySettings
    from app.services.strategy.signals import Signal
    from app.services.trading_engine import TradingEngine

    settings = get_settings()
    monkeypatch.setattr(settings, "trading_market", "futures", raising=False)
    monkeypatch.setattr(settings, "funding_signal_enabled", True, raising=False)
    monkeypatch.setattr(settings, "funding_signal_threshold_pct", 0.0005, raising=False)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    db_session.commit()

    client = AsyncMock()
    client.get_futures_funding_rate = AsyncMock(return_value={"r": "-0.0008"})  # favorable for long
    engine = TradingEngine(db_session, client)
    engine.notifier = AsyncMock()
    sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
    mult = await engine._check_funding_signal("BTC_USDT", sig)
    assert mult == Decimal("1")  # no boost, no de-risk


async def test_funding_signal_de_risks_adverse_short(db_session, monkeypatch):
    """A negative funding rate above the threshold is a headwind for a SHORT."""
    from unittest.mock import AsyncMock

    from app.core.config import get_settings
    from app.models.entities import StrategySettings
    from app.services.strategy.signals import Signal
    from app.services.trading_engine import TradingEngine

    settings = get_settings()
    monkeypatch.setattr(settings, "trading_market", "futures", raising=False)
    monkeypatch.setattr(settings, "funding_signal_enabled", True, raising=False)
    monkeypatch.setattr(settings, "funding_signal_threshold_pct", 0.0005, raising=False)
    monkeypatch.setattr(settings, "funding_signal_risk_mult", 0.5, raising=False)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    db_session.commit()

    client = AsyncMock()
    client.get_futures_funding_rate = AsyncMock(return_value={"r": "-0.0008"})  # adverse for short
    engine = TradingEngine(db_session, client)
    engine.notifier = AsyncMock()
    sig = Signal(True, "short", "short_breakout", Decimal("100"), Decimal("2"))
    mult = await engine._check_funding_signal("BTC_USDT", sig)
    assert mult == Decimal("0.5")


async def test_funding_signal_no_op_on_spot(db_session, monkeypatch):
    from unittest.mock import AsyncMock

    from app.core.config import get_settings
    from app.services.strategy.signals import Signal
    from app.services.trading_engine import TradingEngine

    settings = get_settings()
    monkeypatch.setattr(settings, "trading_market", "spot", raising=False)
    monkeypatch.setattr(settings, "funding_signal_enabled", True, raising=False)

    client = AsyncMock()
    engine = TradingEngine(db_session, client)
    sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
    mult = await engine._check_funding_signal("BTC_USDT", sig)
    assert mult == Decimal("1")
    client.get_futures_funding_rate.assert_not_called()


# --- Order book imbalance (microstructure entry gate) ---


async def test_get_order_book_returns_bids_asks(monkeypatch):
    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        return {
            "bids": [["100.0", "1.5"], ["99.9", "2.0"]],
            "asks": [["100.1", "0.5"], ["100.2", "1.0"]],
        }

    monkeypatch.setattr(c, "request", fake_request)
    book = await c.get_order_book("BTC_USDT", depth=20)
    assert book is not None
    assert len(book["bids"]) == 2
    assert len(book["asks"]) == 2


async def test_get_order_book_returns_none_on_failure(monkeypatch):
    c = GateIOClient()

    async def fake_request(method, path, *, params=None, json_body=None):
        raise RuntimeError("down")

    monkeypatch.setattr(c, "request", fake_request)
    assert await c.get_order_book("BTC_USDT") is None


async def test_orderbook_imbalance_de_risks_long_against_ask_wall(db_session, monkeypatch):
    """A LONG entry when ask depth >> bid depth (sell wall) is de-risked — the
    breakout hits resting sellers and has worse follow-through."""
    from unittest.mock import AsyncMock

    from app.core.config import get_settings
    from app.models.entities import StrategySettings
    from app.services.strategy.signals import Signal
    from app.services.trading_engine import TradingEngine

    settings = get_settings()
    monkeypatch.setattr(settings, "orderbook_imbalance_enabled", True, raising=False)
    monkeypatch.setattr(settings, "orderbook_imbalance_threshold", 0.3, raising=False)
    monkeypatch.setattr(settings, "orderbook_imbalance_risk_mult", 0.5, raising=False)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    db_session.commit()

    # Ask-heavy: bid_depth=3.5, ask_depth=10.5 -> imbalance = -0.5 < -0.3.
    client = AsyncMock()
    client.get_order_book = AsyncMock(return_value={
        "bids": [["100", "1.5"], ["99", "2.0"]],
        "asks": [["101", "5.0"], ["102", "5.5"]],
    })
    engine = TradingEngine(db_session, client)
    engine.notifier = AsyncMock()
    sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
    mult = await engine._check_orderbook_imbalance("BTC_USDT", sig)
    assert mult == Decimal("0.5")


async def test_orderbook_imbalance_de_risks_short_against_bid_wall(db_session, monkeypatch):
    """A SHORT entry when bid depth >> ask depth (buy wall) is de-risked."""
    from unittest.mock import AsyncMock

    from app.core.config import get_settings
    from app.models.entities import StrategySettings
    from app.services.strategy.signals import Signal
    from app.services.trading_engine import TradingEngine

    settings = get_settings()
    monkeypatch.setattr(settings, "orderbook_imbalance_enabled", True, raising=False)
    monkeypatch.setattr(settings, "orderbook_imbalance_threshold", 0.3, raising=False)
    monkeypatch.setattr(settings, "orderbook_imbalance_risk_mult", 0.5, raising=False)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    db_session.commit()

    # Bid-heavy: bid_depth=10.5, ask_depth=3.5 -> imbalance = +0.5 > 0.3 (adverse for short).
    client = AsyncMock()
    client.get_order_book = AsyncMock(return_value={
        "bids": [["100", "5.0"], ["99", "5.5"]],
        "asks": [["101", "1.5"], ["102", "2.0"]],
    })
    engine = TradingEngine(db_session, client)
    engine.notifier = AsyncMock()
    sig = Signal(True, "short", "short_breakout", Decimal("100"), Decimal("2"))
    mult = await engine._check_orderbook_imbalance("BTC_USDT", sig)
    assert mult == Decimal("0.5")


async def test_orderbook_imbalance_no_boost_for_favorable_long(db_session, monkeypatch):
    """Bid-heavy book is favorable for a long (buy support) — but the signal is
    asymmetric: it does NOT boost size (protect capital first)."""
    from unittest.mock import AsyncMock

    from app.core.config import get_settings
    from app.models.entities import StrategySettings
    from app.services.strategy.signals import Signal
    from app.services.trading_engine import TradingEngine

    settings = get_settings()
    monkeypatch.setattr(settings, "orderbook_imbalance_enabled", True, raising=False)
    monkeypatch.setattr(settings, "orderbook_imbalance_threshold", 0.3, raising=False)

    row = db_session.query(StrategySettings).first() or StrategySettings()
    if row.id is None:
        db_session.add(row)
    row.is_enabled = True
    db_session.commit()

    # Bid-heavy (favorable for long): imbalance = +0.5 > 0.3 but NOT adverse for long.
    client = AsyncMock()
    client.get_order_book = AsyncMock(return_value={
        "bids": [["100", "5.0"], ["99", "5.5"]],
        "asks": [["101", "1.5"], ["102", "2.0"]],
    })
    engine = TradingEngine(db_session, client)
    engine.notifier = AsyncMock()
    sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
    mult = await engine._check_orderbook_imbalance("BTC_USDT", sig)
    assert mult == Decimal("1")  # no boost


async def test_orderbook_imbalance_disabled_returns_one(db_session, monkeypatch):
    from unittest.mock import AsyncMock

    from app.core.config import get_settings
    from app.services.strategy.signals import Signal
    from app.services.trading_engine import TradingEngine

    settings = get_settings()
    monkeypatch.setattr(settings, "orderbook_imbalance_enabled", False, raising=False)

    client = AsyncMock()
    engine = TradingEngine(db_session, client)
    sig = Signal(True, "long", "long_breakout", Decimal("100"), Decimal("2"))
    mult = await engine._check_orderbook_imbalance("BTC_USDT", sig)
    assert mult == Decimal("1")
    client.get_order_book.assert_not_called()
