from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.ingestion import _to_datetime
from app.market_data.price_cache import PriceCache
from app.market_data.websocket import GateIOWebSocketClient


def test_price_cache_set_get_and_freshness() -> None:
    cache = PriceCache()
    assert cache.get("BTC_USDT") is None
    cache.set("BTC_USDT", Decimal("50000"))
    assert cache.get("BTC_USDT") == Decimal("50000")
    assert cache.is_fresh("BTC_USDT", max_age_seconds=60) is True
    assert cache.is_fresh("ETH_USDT") is False
    assert cache.snapshot()["BTC_USDT"] == 50000.0


def test_to_datetime_parses_epoch_seconds() -> None:
    ts = _to_datetime("1700000000")
    assert ts == datetime.fromtimestamp(1700000000, UTC)


def test_websocket_handle_message_updates_cache() -> None:
    from app.market_data.price_cache import price_cache

    GateIOWebSocketClient._handle_message(
        '{"channel":"spot.tickers","event":"update",'
        '"result":{"currency_pair":"ETH_USDT","last":"3200.5"}}'
    )
    assert price_cache.get("ETH_USDT") == Decimal("3200.5")


def test_websocket_ignores_non_ticker_messages() -> None:
    # Should not raise on subscribe acks / malformed payloads.
    GateIOWebSocketClient._handle_message('{"event":"subscribe","channel":"spot.tickers"}')
    GateIOWebSocketClient._handle_message("not-json")


def test_subscribe_message_lists_symbols() -> None:
    import json

    client = GateIOWebSocketClient(["BTC_USDT", "ETH_USDT"])
    payload = json.loads(client._subscribe_message())
    assert payload["channel"] == "spot.tickers"
    assert payload["event"] == "subscribe"
    assert payload["payload"] == ["BTC_USDT", "ETH_USDT"]
