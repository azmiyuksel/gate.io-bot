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
