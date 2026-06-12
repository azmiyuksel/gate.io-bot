"""Unit tests for the paper trading worker entry point."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings


@pytest.fixture()
def _settings():
    s = Settings(
        environment="local",
        secret_key="test",
        fernet_key="test",
        trading_symbols="BTC_USDT",
    )
    with patch("app.workers.paper_worker.get_settings", return_value=s):
        yield s


@pytest.mark.asyncio
async def test_paper_worker_creates_default_account(_settings):
    """If no PaperAccount exists, one must be created."""
    with patch("app.workers.paper_worker.SessionLocal") as mock_session_cls, \
         patch("app.workers.paper_worker.PaperTradingEngine") as mock_engine_cls, \
         patch("app.workers.paper_worker.CapitalPreservationAdapter"):

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        # No existing account
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_engine = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        from app.workers.paper_worker import main
        await main()

        # A PaperAccount should have been added
        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        mock_engine.start.assert_awaited_once_with(_settings.symbols)


@pytest.mark.asyncio
async def test_paper_worker_reuses_existing_account(_settings):
    """If a PaperAccount already exists, it should be reused."""
    with patch("app.workers.paper_worker.SessionLocal") as mock_session_cls, \
         patch("app.workers.paper_worker.PaperTradingEngine") as mock_engine_cls, \
         patch("app.workers.paper_worker.CapitalPreservationAdapter"):

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        existing_account = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_account

        mock_engine = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        from app.workers.paper_worker import main
        await main()

        # No new account should be added
        mock_db.add.assert_not_called()
        mock_engine.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_paper_worker_always_closes_db(_settings):
    """DB session must be closed even if the engine raises."""
    with patch("app.workers.paper_worker.SessionLocal") as mock_session_cls, \
         patch("app.workers.paper_worker.PaperTradingEngine") as mock_engine_cls, \
         patch("app.workers.paper_worker.CapitalPreservationAdapter"):

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()

        mock_engine = AsyncMock()
        mock_engine.start.side_effect = RuntimeError("exchange down")
        mock_engine_cls.return_value = mock_engine

        from app.workers.paper_worker import main
        with pytest.raises(RuntimeError, match="exchange down"):
            await main()

        mock_db.close.assert_called_once()
