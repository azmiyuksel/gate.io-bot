"""Regression tests for the critical hardening fixes.

Covers: strategy zero-price guard, exchange retry classification, equity
staleness detection and resilient Telegram notifications.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.account.engine import AccountManager
from app.account.models import EquitySnapshot
from app.services.exchange.gateio import GateIOClient
from app.services.notifications.telegram import TelegramNotifier
from app.services.strategy.signals import CapitalPreservationStrategy


def _candle(close: float) -> dict:
    return {
        "open": Decimal(str(close)),
        "high": Decimal(str(close)),
        "low": Decimal(str(close)),
        "close": Decimal(str(close)),
        "volume": Decimal("1"),
        "timestamp": 0,
    }


def test_strategy_guards_against_zero_price() -> None:
    # 209 healthy candles followed by a corrupt zero-price candle.
    candles = [_candle(100.0) for _ in range(209)] + [_candle(0.0)]
    signal = CapitalPreservationStrategy().evaluate(candles)
    assert signal.should_buy is False
    assert signal.reason == "invalid_price_data"


async def test_request_fails_fast_on_4xx(monkeypatch) -> None:
    client = GateIOClient()
    calls = 0

    async def fake_request(*args, **kwargs):
        nonlocal calls
        calls += 1
        request = httpx.Request("GET", "https://example/x")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(client.client, "request", fake_request)
    with pytest.raises(httpx.HTTPStatusError):
        await client.request("GET", "/spot/accounts")
    assert calls == 1  # 401 is not retried
    await client.close()


async def test_request_retries_on_429(monkeypatch) -> None:
    client = GateIOClient()
    calls = 0

    async def fake_request(*args, **kwargs):
        nonlocal calls
        calls += 1
        request = httpx.Request("GET", "https://example/x")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(client.client, "request", fake_request)
    monkeypatch.setattr("app.services.exchange.gateio.asyncio.sleep", no_sleep)
    with pytest.raises(httpx.HTTPStatusError):
        await client.request("GET", "/spot/accounts")
    assert calls == 3  # retried up to the attempt limit
    await client.close()


def test_equity_stale_without_snapshot(db_session) -> None:
    manager = AccountManager(db_session)
    assert manager.snapshot_age_seconds() is None
    assert manager.is_equity_stale() is True


def test_equity_freshness(db_session) -> None:
    manager = AccountManager(db_session)
    snapshot = EquitySnapshot(
        cash_balance=Decimal("10000"),
        available_balance=Decimal("10000"),
        locked_balance=Decimal("0"),
        positions_value=Decimal("0"),
        total_equity=Decimal("10000"),
    )
    manager.persist(snapshot)
    assert manager.is_equity_stale() is False

    # Backdate the snapshot beyond the staleness window.
    record = manager.last_snapshot()
    record.created_at = datetime.now(UTC) - timedelta(
        seconds=manager.settings.max_equity_staleness_seconds + 60
    )
    db_session.commit()
    assert manager.is_equity_stale() is True


async def test_telegram_send_swallows_errors(monkeypatch) -> None:
    notifier = TelegramNotifier()
    # Force credentials so send() actually attempts a request.
    settings = notifier.send.__globals__["get_settings"]()
    monkeypatch.setattr(settings, "telegram_bot_token", "x", raising=False)
    monkeypatch.setattr(settings, "telegram_chat_id", "y", raising=False)

    class BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.ConnectError("down")

    monkeypatch.setattr("app.services.notifications.telegram.httpx.AsyncClient", BoomClient)
    # Must not raise despite the transport failure.
    await notifier.send("hello")
