"""Unit tests for the scheduler worker entry points.

All external I/O (exchange, DB, Telegram) is mocked so the tests run fast
and offline.
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings


@pytest.fixture()
def _settings():
    """Patch get_settings for scheduler tests."""
    s = Settings(
        environment="local",
        secret_key="test",
        fernet_key="test",
        bot_enabled=False,
        gateio_api_key="",
        gateio_api_secret="",
        telegram_bot_token="",
        telegram_chat_id="",
        trading_symbols="BTC_USDT",
    )
    with patch("app.workers.scheduler.get_settings", return_value=s):
        yield s


@pytest.mark.asyncio
async def test_run_cycle_skips_when_bot_disabled(_settings):
    """run_cycle must bail early when BOT_ENABLED is False."""
    with patch("app.workers.scheduler.SessionLocal") as mock_session_cls, \
         patch("app.workers.scheduler.GateIOClient") as mock_client_cls, \
         patch("app.workers.scheduler.ReconciliationEngine") as mock_recon, \
         patch("app.workers.scheduler.AccountManager") as mock_acct, \
         patch("app.workers.scheduler.CircuitBreaker") as mock_breaker, \
         patch("app.workers.scheduler.TradingEngine") as mock_engine, \
         patch("app.workers.scheduler.StrategySettingsRepository") as mock_settings_repo:

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.close = AsyncMock()

        mock_recon_inst = AsyncMock()
        mock_recon.return_value = mock_recon_inst

        mock_acct_inst = MagicMock()
        mock_acct.return_value = mock_acct_inst
        snapshot = MagicMock()
        snapshot.total_equity = Decimal("10000")
        snapshot.source = "exchange"
        mock_acct_inst.refresh = AsyncMock(return_value=snapshot)
        mock_acct_inst.drawdown_pct.return_value = Decimal("0")

        mock_breaker_inst = MagicMock()
        mock_breaker.return_value = mock_breaker_inst
        mock_breaker_inst.check_and_trip.return_value = False

        mock_settings_inst = MagicMock()
        mock_settings_repo.return_value = mock_settings_inst
        mock_settings_inst.current.return_value = MagicMock(is_enabled=False)

        mock_engine_inst = MagicMock()
        mock_engine_inst.manage_open_positions = AsyncMock()
        mock_engine.return_value = mock_engine_inst

        from app.workers.scheduler import run_cycle
        await run_cycle()

        # TradingEngine.scan_symbol must NOT be called when bot is disabled
        mock_engine_inst.scan_symbol.assert_not_called()


@pytest.mark.asyncio
async def test_run_cycle_skips_when_strategy_disabled(_settings):
    """run_cycle must bail early when strategy is_enabled is False."""
    _settings.bot_enabled = True

    with patch("app.workers.scheduler.SessionLocal") as mock_session_cls, \
         patch("app.workers.scheduler.GateIOClient") as mock_client_cls, \
         patch("app.workers.scheduler.ReconciliationEngine") as mock_recon, \
         patch("app.workers.scheduler.AccountManager") as mock_acct, \
         patch("app.workers.scheduler.CircuitBreaker") as mock_breaker, \
         patch("app.workers.scheduler.TradingEngine") as mock_engine, \
         patch("app.workers.scheduler.StrategySettingsRepository") as mock_settings_repo:

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.close = AsyncMock()

        mock_recon.return_value = AsyncMock()

        mock_acct_inst = MagicMock()
        mock_acct.return_value = mock_acct_inst
        snapshot = MagicMock()
        snapshot.total_equity = Decimal("10000")
        snapshot.source = "exchange"
        mock_acct_inst.refresh = AsyncMock(return_value=snapshot)
        mock_acct_inst.drawdown_pct.return_value = Decimal("0")

        mock_breaker.return_value = MagicMock(check_and_trip=MagicMock(return_value=False))

        mock_settings_inst = MagicMock()
        mock_settings_repo.return_value = mock_settings_inst
        mock_settings_inst.current.return_value = MagicMock(is_enabled=False)

        mock_engine_inst = MagicMock()
        mock_engine_inst.manage_open_positions = AsyncMock()
        mock_engine.return_value = mock_engine_inst

        from app.workers.scheduler import run_cycle
        await run_cycle()

        # TradingEngine.scan_symbol must NOT be called when strategy disabled
        mock_engine_inst.scan_symbol.assert_not_called()


@pytest.mark.asyncio
async def test_run_cycle_trips_circuit_breaker(_settings):
    """When the circuit breaker is tripped, run_cycle must open NO new
    entries. Position management now runs on a SEPARATE fast cadence
    (monitor_positions), so manage_open_positions is NOT called from
    run_cycle anymore."""
    _settings.bot_enabled = True

    with patch("app.workers.scheduler.SessionLocal") as mock_session_cls, \
         patch("app.workers.scheduler.GateIOClient") as mock_client_cls, \
         patch("app.workers.scheduler.ReconciliationEngine") as mock_recon, \
         patch("app.workers.scheduler.AccountManager") as mock_acct, \
         patch("app.workers.scheduler.CircuitBreaker") as mock_breaker, \
         patch("app.workers.scheduler.TradingEngine") as mock_engine, \
         patch("app.workers.scheduler.StrategySettingsRepository"):

        mock_session_cls.return_value = MagicMock()
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.close = AsyncMock()
        mock_recon.return_value = AsyncMock()

        mock_acct_inst = MagicMock()
        mock_acct.return_value = mock_acct_inst
        snapshot = MagicMock()
        snapshot.total_equity = Decimal("10000")
        snapshot.source = "exchange"
        mock_acct_inst.refresh = AsyncMock(return_value=snapshot)
        mock_acct_inst.drawdown_pct.return_value = Decimal("0.20")

        mock_breaker_inst = MagicMock()
        mock_breaker.return_value = mock_breaker_inst
        mock_breaker_inst.check_and_trip.return_value = True

        mock_engine_inst = MagicMock()
        mock_engine_inst.manage_open_positions = AsyncMock()
        mock_engine.return_value = mock_engine_inst

        from app.workers.scheduler import run_cycle
        await run_cycle()

        # Position management now runs on a SEPARATE fast cadence
        # (monitor_positions), not inside run_cycle — so manage_open_positions
        # is NOT called from run_cycle anymore. The circuit breaker still trips
        # and no new entries are opened.
        mock_engine_inst.manage_open_positions.assert_not_called()
        # ...but no new entries may be opened.
        mock_engine_inst.scan_symbol.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_market_data_closes_resources(_settings):
    """ingest_market_data must always close the client and db session."""
    with patch("app.workers.scheduler.SessionLocal") as mock_session_cls, \
         patch("app.workers.scheduler.GateIOClient") as mock_client_cls, \
         patch("app.workers.scheduler.MarketDataIngestion") as mock_ingest:

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.close = AsyncMock()

        mock_ingest.return_value = AsyncMock()

        from app.workers.scheduler import ingest_market_data
        await ingest_market_data()

        mock_client.close.assert_awaited_once()
        mock_db.close.assert_called_once()
