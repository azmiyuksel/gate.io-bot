"""Tests for live-trading preflight checks."""
from app.core.config import Settings
from app.workers.preflight import (
    config_preflight,
    exchange_preflight,
    format_issues,
    has_blocking_errors,
)


def _settings(**overrides) -> Settings:
    base = dict(
        environment="production",
        secret_key="a-strong-random-secret",
        fernet_key="some-fernet-key",
        bot_enabled=True,
        gateio_api_key="key",
        gateio_api_secret="secret",
        telegram_bot_token="token",
        telegram_chat_id="chat",
        worker_watchdog_enabled=True,
        trading_market="spot",
    )
    base.update(overrides)
    return Settings(**base)


def test_disabled_bot_has_no_issues() -> None:
    assert config_preflight(_settings(bot_enabled=False)) == []


def test_fully_configured_live_has_no_issues() -> None:
    assert config_preflight(_settings()) == []


def test_missing_api_keys_is_blocking_error() -> None:
    issues = config_preflight(_settings(gateio_api_key="", gateio_api_secret=""))
    codes = {i.code: i.level for i in issues}
    assert codes.get("missing_api_keys") == "error"
    assert has_blocking_errors(issues) is True


def test_weak_secret_is_blocking_error() -> None:
    issues = config_preflight(_settings(secret_key="change-me"))
    assert any(i.code == "weak_secret_key" and i.level == "error" for i in issues)


def test_non_production_and_missing_alerting_are_warnings() -> None:
    issues = config_preflight(_settings(
        environment="local",
        telegram_bot_token="",
        telegram_chat_id="",
        worker_watchdog_enabled=False,
        fernet_key="",
    ))
    codes = {i.code for i in issues}
    assert {"environment_not_production", "telegram_unconfigured",
            "watchdog_disabled", "fernet_unset"} <= codes
    # None of these are blocking on their own.
    assert all(i.level == "warning" for i in issues if i.code in codes - {"missing_api_keys"})


def test_futures_market_warns_experimental() -> None:
    issues = config_preflight(_settings(trading_market="futures"))
    assert any(i.code == "futures_experimental" and i.level == "warning" for i in issues)


def test_format_issues_empty_and_nonempty() -> None:
    assert "geçti" in format_issues([])
    msg = format_issues(config_preflight(_settings(gateio_api_key="", gateio_api_secret="")))
    assert "❌" in msg


async def test_exchange_preflight_flags_unreachable() -> None:
    class FailingClient:
        async def balances(self):
            raise RuntimeError("401 unauthorized")

    issues = await exchange_preflight(_settings(), FailingClient())
    assert any(i.code == "exchange_unreachable" and i.level == "error" for i in issues)


async def test_exchange_preflight_warns_on_zero_balance() -> None:
    class EmptyClient:
        async def balances(self):
            return [{"currency": "USDT", "available": "0", "locked": "0"}]

    issues = await exchange_preflight(_settings(), EmptyClient())
    assert any(i.code == "no_quote_balance" for i in issues)


async def test_exchange_preflight_passes_with_balance() -> None:
    class FundedClient:
        async def balances(self):
            return [{"currency": "USDT", "available": "1000", "locked": "0"}]

    assert await exchange_preflight(_settings(), FundedClient()) == []


async def test_exchange_preflight_skipped_when_disabled() -> None:
    class Boom:
        async def balances(self):
            raise AssertionError("should not be called")

    assert await exchange_preflight(_settings(bot_enabled=False), Boom()) == []
