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


# --- Paper engine redesign: real-candle entries, tick-only exits ---


def test_evaluate_real_candles_maps_strategy_signal(monkeypatch):
    from decimal import Decimal

    from app.paper_trading.models import PaperSide
    from app.paper_trading.strategy_adapter import CapitalPreservationAdapter
    from app.services.strategy.signals import Signal

    adapter = CapitalPreservationAdapter()
    monkeypatch.setattr(
        adapter._strategy, "evaluate",
        lambda candles: Signal(True, "long_entry", Decimal("100"), Decimal("2")),
    )
    sig = adapter.evaluate_real_candles("BTC_USDT", [{}])
    assert sig is not None
    assert sig.side == PaperSide.buy
    assert sig.metadata["atr"] == "2"
    assert sig.metadata["entry"] == "100"

    monkeypatch.setattr(
        adapter._strategy, "evaluate", lambda candles: Signal(False, "rsi_not_oversold")
    )
    assert adapter.evaluate_real_candles("BTC_USDT", [{}]) is None


def test_stream_tick_has_no_intrabar_range():
    import json

    from app.paper_trading.market_data_stream import GateIOMarketDataStream

    stream = GateIOMarketDataStream(["BTC_USDT"])
    raw = json.dumps({
        "result": {
            "last": "100", "currency_pair": "BTC_USDT",
            "base_volume": "5", "high_24h": "130", "low_24h": "70",
        }
    })
    data = stream._parse(raw)
    # 24h high/low must NOT leak into per-tick bar fields.
    assert data.price == 100.0
    assert data.high is None
    assert data.low is None


def test_signal_diagnostics_aggregates_skip_reasons(db_session):
    from datetime import UTC, datetime

    from app.api.v1.paper import _get_or_create_account, signal_diagnostics
    from app.models.entities import PaperLog

    account = _get_or_create_account(db_session)
    rows = [
        ("entry_skipped", "BTC_USDT", "below_200_ema"),
        ("entry_skipped", "ETH_USDT", "rsi_not_oversold"),
        ("entry_skipped", "BTC_USDT", "below_200_ema"),
        ("risk_check", "SOL_USDT", "max_open_positions"),
        ("risk_check", "ADA_USDT", "approved"),
    ]
    for event, symbol, reason in rows:
        db_session.add(PaperLog(
            account_id=account.id, event=event,
            message=f"{symbol}: {reason}",
            payload={"symbol": symbol, "reason": reason},
            created_at=datetime.now(UTC),
        ))
    db_session.commit()

    result = signal_diagnostics(db_session, hours=24)
    assert result["evaluations"] == 5
    assert result["reason_counts"]["below_200_ema"] == 2
    assert result["reason_counts"]["approved"] == 1
    # Counts are returned in descending order (most frequent first).
    assert list(result["reason_counts"])[0] == "below_200_ema"
    # Latest reason is tracked per symbol.
    assert result["latest_by_symbol"]["BTC_USDT"]["reason"] == "below_200_ema"


def test_paper_economics_edge_and_cost_bridge(db_session):
    from decimal import Decimal

    from app.api.v1.paper import _get_or_create_account, economics
    from app.models.entities import PaperTrade
    from app.models.enums import OrderSide

    account = _get_or_create_account(db_session)
    account.realized_pnl = Decimal("30")  # net of fees
    for pnl, fee in (("20", "1"), ("20", "1"), ("-10", "1")):
        db_session.add(PaperTrade(
            account_id=account.id, order_id=None, symbol="BTC_USDT", side=OrderSide.sell,
            price=Decimal("100"), quantity=Decimal("1"), fee=Decimal(fee), realized_pnl=Decimal(pnl),
        ))
    db_session.commit()

    result = economics(db_session)
    assert result["edge"]["trades"] == 3
    assert result["edge"]["has_edge"] is True
    assert round(result["edge"]["expectancy_r"], 6) == 1.0       # expectancy 10 / avg loss 10
    # Cost bridge: gross = net + fees.
    assert result["cost_bridge"]["net_pnl"] == 30.0
    assert result["cost_bridge"]["total_fees"] == 3.0
    assert result["cost_bridge"]["gross_pnl"] == 33.0
