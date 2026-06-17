"""Unit tests for the paper trading worker entry point."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.models.enums import PaperBotStatus


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
         patch("app.workers.paper_worker.CapitalPreservationAdapter"), \
         patch("app.workers.paper_worker.PaperAccount") as mock_account_cls, \
         patch("app.workers.paper_worker.PaperPortfolio") as mock_portfolio_cls:

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        # No existing account
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # The newly-created account is RUNNING so the worker proceeds to start
        # the engine (rather than waiting on the user's start signal).
        new_account = MagicMock()
        new_account.status = PaperBotStatus.running
        new_account.cash_balance = 10000
        mock_account_cls.return_value = new_account

        mock_engine = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        mock_portfolio = MagicMock()
        mock_portfolio_cls.return_value = mock_portfolio

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
         patch("app.workers.paper_worker.CapitalPreservationAdapter"), \
         patch("app.workers.paper_worker.PaperPortfolio") as mock_portfolio_cls:

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        existing_account = MagicMock()
        existing_account.cash_balance = 10000
        existing_account.status = PaperBotStatus.running
        mock_db.query.return_value.filter.return_value.first.return_value = existing_account

        mock_engine = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        mock_portfolio = MagicMock()
        mock_portfolio_cls.return_value = mock_portfolio

        from app.workers.paper_worker import main
        await main()

        # No new account should be added
        mock_db.add.assert_not_called()
        mock_engine.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_paper_worker_retries_then_exits_closing_db(_settings, monkeypatch):
    """The worker retries (rather than crashing) when the engine errors, and the
    DB session is closed on every iteration. It exits the retry loop once start()
    returns normally."""
    # No real backoff sleeps, so the test can't hang on the worker's retry loop.
    monkeypatch.setattr("app.workers.paper_worker.asyncio.sleep", AsyncMock())
    with patch("app.workers.paper_worker.SessionLocal") as mock_session_cls, \
         patch("app.workers.paper_worker.PaperTradingEngine") as mock_engine_cls, \
         patch("app.workers.paper_worker.CapitalPreservationAdapter"), \
         patch("app.workers.paper_worker.PaperPortfolio") as mock_portfolio_cls:

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        running_account = MagicMock()
        running_account.cash_balance = 10000
        running_account.status = PaperBotStatus.running
        mock_db.query.return_value.filter.return_value.first.return_value = running_account

        mock_engine = AsyncMock()
        # Fail once (worker should retry), then succeed so the loop breaks.
        mock_engine.start.side_effect = [RuntimeError("exchange down"), None]
        mock_engine_cls.return_value = mock_engine
        mock_portfolio_cls.return_value = MagicMock()

        from app.workers.paper_worker import main
        await main()

        assert mock_engine.start.await_count == 2          # retried after the error
        assert mock_db.close.call_count >= 2               # db closed each iteration


# --- Paper engine redesign: real-candle entries, tick-only exits ---


def test_evaluate_real_candles_maps_strategy_signal(monkeypatch):
    from decimal import Decimal

    from app.paper_trading.models import PaperSide
    from app.paper_trading.strategy_adapter import CapitalPreservationAdapter
    from app.services.strategy.signals import Signal

    adapter = CapitalPreservationAdapter()
    monkeypatch.setattr(
        adapter._strategy, "evaluate",
        lambda candles: Signal(True, "long", "long_entry", Decimal("100"), Decimal("2")),
    )
    sig = adapter.evaluate_real_candles("BTC_USDT", [{}])
    assert sig is not None
    assert sig.side == PaperSide.buy
    assert sig.metadata["atr"] == "2"
    assert sig.metadata["entry"] == "100"

    monkeypatch.setattr(
        adapter._strategy, "evaluate", lambda candles: Signal(False, "", "rsi_not_oversold")
    )
    assert adapter.evaluate_real_candles("BTC_USDT", [{}]) is None


def test_adapter_reason_code_is_stable_without_rsi(monkeypatch):
    """The diagnostics payload must use a STABLE reason code (no embedded RSI),
    otherwise every evaluation is a unique reason and the tally grows unbounded."""
    from app.paper_trading.strategy_adapter import CapitalPreservationAdapter
    from app.services.strategy.signals import Signal

    adapter = CapitalPreservationAdapter()
    monkeypatch.setattr(
        adapter._strategy, "evaluate",
        lambda candles: Signal(False, "", "rsi_not_oversold", diagnostics={"rsi": 43.14159}),
    )
    adapter.evaluate_real_candles("BTC_USDT", [{}])
    # Groupable code carries no RSI; human-readable message still shows it.
    assert adapter.last_reason_code == "rsi_not_oversold"
    assert "RSI" in adapter.last_reason


def test_short_close_settles_cash_without_inflating_equity(db_session):
    """Closing a SHORT must settle cash as a buy-back (pay exit cost), not reuse the
    long formula (entry*qty + pnl) which double-credits the open proceeds and makes
    equity climb on every short — even losers. Equity must be continuous across the
    close: a losing short LOWERS equity, a winning short raises it by ~pnl only."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from app.models.entities import PaperAccount, PaperPosition
    from app.paper_trading.broker import PaperBroker
    from app.paper_trading.models import MarketData
    from app.paper_trading.portfolio import PaperPortfolio

    now = datetime.now(UTC)

    def _open_short(name: str) -> tuple[PaperAccount, PaperPosition]:
        # Short 1 @ 100: opening credits proceeds, so cash went 10000 -> ~10100.
        acc = PaperAccount(name=name, cash_balance=Decimal("10100"), initial_balance=Decimal("10000"))
        db_session.add(acc)
        db_session.commit()
        db_session.refresh(acc)
        pos = PaperPosition(
            account_id=acc.id, symbol="AAA_USDT", side="sell",
            quantity=Decimal("1"), average_entry_price=Decimal("100"), last_price=Decimal("100"),
        )
        db_session.add(pos)
        db_session.commit()
        return acc, pos

    # Losing short: price rose to 110. Equity must drop below the 10000 start.
    acc, pos = _open_short("short_loss")
    PaperBroker(db_session, acc).close_position(pos, MarketData("AAA_USDT", now, 110.0), "stop_loss")
    db_session.commit()
    equity = PaperPortfolio(db_session, acc).equity()
    assert equity < Decimal("10000")          # a loss reduces equity
    assert equity < Decimal("10100")          # and is NOT the inflated open-cash value

    # Winning short: price fell to 90. Equity rises, but only by ~10 (not ~+100).
    acc2, pos2 = _open_short("short_win")
    PaperBroker(db_session, acc2).close_position(pos2, MarketData("AAA_USDT", now, 90.0), "take_profit")
    db_session.commit()
    equity2 = PaperPortfolio(db_session, acc2).equity()
    assert Decimal("10000") < equity2 < Decimal("10025")


def test_equity_counts_position_market_value(db_session):
    """Open positions must contribute their market value to equity. A long buy
    deducts the full notional from cash, so if equity only added unrealized PnL it
    would understate by the cost basis (~the whole notional) and instantly trip the
    daily-loss guard — the 'one buy then pause' bug. Shorts must subtract the
    liability rather than inflate equity."""
    from decimal import Decimal

    from app.models.entities import PaperAccount, PaperPosition
    from app.paper_trading.portfolio import PaperPortfolio

    acc = PaperAccount(name="default", cash_balance=Decimal("9500"), initial_balance=Decimal("10000"))
    db_session.add(acc)
    db_session.commit()
    db_session.refresh(acc)
    # Bought 5 @ 100 (=500 notional): cash went 10000 -> 9500.
    db_session.add(PaperPosition(
        account_id=acc.id, symbol="AAA_USDT", side="buy",
        quantity=Decimal("5"), average_entry_price=Decimal("100"), last_price=Decimal("100"),
    ))
    db_session.commit()
    port = PaperPortfolio(db_session, acc)
    # cash 9500 + market value 500 = 10000 (no phantom 5% loss).
    assert port.equity() == Decimal("10000")
    # Price up 2% -> +10 unrealized.
    pos = port.open_positions()[0]
    pos.last_price = Decimal("102")
    db_session.commit()
    assert port.equity() == Decimal("10010")

    # Short: sell 5 @ 100 inflates cash to 10500; equity must subtract the 500
    # liability back to ~10000 (not report a 5% gain).
    short_acc = PaperAccount(name="s", cash_balance=Decimal("10500"), initial_balance=Decimal("10000"))
    db_session.add(short_acc)
    db_session.commit()
    db_session.refresh(short_acc)
    db_session.add(PaperPosition(
        account_id=short_acc.id, symbol="BBB_USDT", side="sell",
        quantity=Decimal("5"), average_entry_price=Decimal("100"), last_price=Decimal("100"),
    ))
    db_session.commit()
    assert PaperPortfolio(db_session, short_acc).equity() == Decimal("10000")


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


def test_status_exposes_pause_reason_when_paused(db_session):
    from app.api.v1.paper import _get_or_create_account, status
    from app.models.entities import PaperLog
    from app.models.enums import PaperBotStatus

    account = _get_or_create_account(db_session)
    account.status = PaperBotStatus.paused
    db_session.add(PaperLog(account_id=account.id, event="system_paused", message="max_drawdown_reached"))
    db_session.commit()

    out = status(db_session)
    assert out.status == PaperBotStatus.paused
    assert out.pause_reason == "max_drawdown_reached"
