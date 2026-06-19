"""Per-strategy breakdown + filter on the /dashboard/economics endpoint."""
from datetime import UTC, datetime
from decimal import Decimal

from app.api.v1.dashboard import economics
from app.models.entities import Trade
from app.models.enums import OrderSide


def _trade(db, strategy, pnl, day):
    db.add(Trade(
        strategy_name=strategy, symbol="BTC_USDT", side=OrderSide.sell,
        price=Decimal("100"), quantity=Decimal("1"), fee=Decimal("0"),
        realized_pnl=Decimal(str(pnl)), traded_at=datetime(2026, 1, day, tzinfo=UTC),
    ))


def test_economics_breaks_down_by_strategy(db_session):
    # Momentum: net winner. Reversion: net loser.
    _trade(db_session, "momentum_breakout_v1", 30, 1)
    _trade(db_session, "momentum_breakout_v1", 20, 2)
    _trade(db_session, "capital_preservation_v1", -10, 3)
    _trade(db_session, "capital_preservation_v1", -5, 4)
    db_session.commit()

    result = economics(db_session)
    by = result["by_strategy"]
    assert set(by) == {"momentum_breakout_v1", "capital_preservation_v1"}
    assert by["momentum_breakout_v1"]["trades"] == 2
    assert by["momentum_breakout_v1"]["expectancy"] == 25.0
    assert by["capital_preservation_v1"]["expectancy"] == -7.5
    # Blended edge mixes both (3 net over 4 trades).
    assert result["strategy_filter"] is None
    assert result["edge"]["trades"] == 4


def test_economics_strategy_filter(db_session):
    _trade(db_session, "momentum_breakout_v1", 30, 1)
    _trade(db_session, "momentum_breakout_v1", 20, 2)
    _trade(db_session, "capital_preservation_v1", -10, 3)
    db_session.commit()

    result = economics(db_session, strategy="momentum_breakout_v1")
    assert result["strategy_filter"] == "momentum_breakout_v1"
    # Edge reflects ONLY the filtered strategy's trades.
    assert result["edge"]["trades"] == 2
    assert result["edge"]["expectancy"] == 25.0
    # by_strategy still shows every strategy regardless of the filter.
    assert set(result["by_strategy"]) == {"momentum_breakout_v1", "capital_preservation_v1"}
