"""Session / time-of-day entry filter."""
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.services.strategy.session import entry_allowed

# 2022-01-01 was a Saturday (weekday 5); 2022-01-03 a Monday (weekday 0).
SAT = datetime(2022, 1, 1, 12, 0, tzinfo=UTC)
MON = datetime(2022, 1, 3, 12, 0, tzinfo=UTC)


def _settings(**over):
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT")
    base.update(over)
    return Settings(**base)


def test_no_op_when_unconfigured():
    assert entry_allowed(MON, set(), False) == (True, "allowed")
    assert entry_allowed(SAT, set(), False)[0] is True


def test_blocks_configured_hour():
    blocked, reason = entry_allowed(datetime(2022, 1, 3, 3, 0, tzinfo=UTC), {3}, False)
    assert blocked is False
    assert "low_liquidity_hour_block" in reason
    # A different hour is allowed.
    assert entry_allowed(datetime(2022, 1, 3, 4, 0, tzinfo=UTC), {3}, False)[0] is True


def test_blocks_weekend_when_enabled():
    blocked, reason = entry_allowed(SAT, set(), True)
    assert blocked is False
    assert "weekend_session_block" in reason
    # Weekday is fine.
    assert entry_allowed(MON, set(), True)[0] is True
    # Weekend allowed when the flag is off.
    assert entry_allowed(SAT, set(), False)[0] is True


def test_blocked_hours_property_parsing():
    s = _settings(session_blocked_hours_utc="0,1, 2 ,x,25,23")
    assert s.session_blocked_hours_set == {0, 1, 2, 23}


def test_engine_session_disabled_allows(db_session):
    from app.services.trading_engine import TradingEngine

    with patch("app.services.trading_engine.get_settings", return_value=_settings(session_filter_enabled=False)):
        engine = TradingEngine(db_session, AsyncMock())
        assert engine._session_allows_entry("BTC_USDT") is True


def test_engine_session_blocks_all_hours(db_session):
    from app.models.entities import SystemLog
    from app.services.trading_engine import TradingEngine

    all_hours = ",".join(str(h) for h in range(24))
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(session_filter_enabled=True, session_blocked_hours_utc=all_hours)):
        engine = TradingEngine(db_session, AsyncMock())
        assert engine._session_allows_entry("BTC_USDT") is False
    logs = db_session.query(SystemLog).filter(SystemLog.source == "session_filter").all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_engine_scan_short_circuits_on_session_block(db_session):
    """scan_symbol must not fetch candles when the session filter blocks."""
    from app.services.trading_engine import TradingEngine

    client = AsyncMock()
    all_hours = ",".join(str(h) for h in range(24))
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(session_filter_enabled=True, session_blocked_hours_utc=all_hours)):
        engine = TradingEngine(db_session, client)
        await engine.scan_symbol("BTC_USDT", Decimal("10000"))
    client.candles.assert_not_called()
