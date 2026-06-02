from decimal import Decimal

from app.account.engine import AccountManager
from app.account.models import EquitySnapshot


def _snapshot(equity: str) -> EquitySnapshot:
    value = Decimal(equity)
    return EquitySnapshot(
        cash_balance=value,
        available_balance=value,
        locked_balance=Decimal("0"),
        positions_value=Decimal("0"),
        total_equity=value,
    )


def test_latest_equity_falls_back_without_snapshot(db_session) -> None:
    manager = AccountManager(db_session)
    # No snapshot yet -> configured fallback (default 10000).
    assert manager.latest_equity() == Decimal("10000")


def test_persist_and_peak_drawdown(db_session) -> None:
    manager = AccountManager(db_session)
    manager.persist(_snapshot("10000"))
    manager.persist(_snapshot("12000"))
    manager.persist(_snapshot("9000"))

    assert manager.latest_equity() == Decimal("9000")
    assert manager.peak_equity() == Decimal("12000")
    # drawdown = (12000 - 9000) / 12000 = 0.25
    assert manager.drawdown_pct() == Decimal("0.25")


async def test_stablecoins_counted_as_cash_not_positions(db_session) -> None:
    # USDC (a non-quote stablecoin) must count as cash at par, not be priced
    # as a position. BTC stays a marked-to-market position.
    from decimal import Decimal

    class FakeClient:
        async def balances(self):
            return [
                {"currency": "USDT", "available": "1000", "locked": "0"},
                {"currency": "USDC", "available": "500", "locked": "0"},
                {"currency": "BTC", "available": "1", "locked": "0"},
            ]
        async def last_price(self, symbol):
            return Decimal("50000") if symbol.startswith("BTC") else None

    manager = AccountManager(db_session, FakeClient())
    snap = await manager.fetch_snapshot()
    assert snap.cash_balance == Decimal("1500")        # USDT + USDC at par
    assert snap.positions_value == Decimal("50000")    # BTC marked to market
    assert snap.total_equity == Decimal("51500")
