"""Tests for the portfolio risk upgrades: holdings-based stress test and VaR/CVaR."""
from decimal import Decimal

from app.models.entities import Portfolio, PortfolioAsset
from app.portfolio.engine import PortfolioEngine
from app.portfolio.risk_model import PortfolioRiskModel


def test_historical_var_cvar_zero_when_only_gains():
    equity = [100, 101, 102, 103, 104, 105]  # monotonic up -> no loss tail
    out = PortfolioRiskModel.historical_var_cvar(equity, 0.95)
    assert out["var"] == 0.0
    assert out["cvar"] == 0.0


def test_historical_var_cvar_positive_with_drawdowns():
    equity = [100, 80, 100, 80, 100, 80, 100]  # alternating -20% / +25%
    out = PortfolioRiskModel.historical_var_cvar(equity, 0.95)
    assert out["var"] > 0.1  # ~20% loss at the tail
    assert out["cvar"] >= out["var"]


def test_stress_test_shocks_actual_holdings_not_equity(db_session):
    # 9,000 cash + a 1,000 position = 10,000 equity. A 30% crash must hit only
    # the 1,000 of exposure (loss 300), NOT 30% of total equity (3,000).
    portfolio = Portfolio(
        name="default",
        total_equity=Decimal("10000"),
        cash_balance=Decimal("9000"),
        daily_max_risk_pct=Decimal("0.02"),
    )
    db_session.add(portfolio)
    db_session.commit()
    db_session.add(
        PortfolioAsset(
            portfolio_id=portfolio.id,
            symbol="BTC_USDT",
            position_size=Decimal("10"),
            average_entry_price=Decimal("100"),
            current_price=Decimal("100"),
        )
    )
    db_session.commit()

    snapshot = PortfolioEngine(db_session, portfolio).run_stress_testing("market_crash_30")
    assert abs(float(snapshot.simulated_loss) - 300.0) < 1e-6
    assert snapshot.metrics_snapshot["position_value"] == 1000.0
    # Loss is 3% of equity (300/10000) which exceeds the 2% daily budget.
    assert snapshot.limit_status == "violated"


def test_stress_test_mostly_cash_barely_moves(db_session):
    # All cash, no positions: a crash scenario produces ~zero loss.
    portfolio = Portfolio(
        name="default", total_equity=Decimal("10000"), cash_balance=Decimal("10000")
    )
    db_session.add(portfolio)
    db_session.commit()
    snapshot = PortfolioEngine(db_session, portfolio).run_stress_testing("flash_crash")
    assert float(snapshot.simulated_loss) == 0.0
    assert snapshot.limit_status == "normal"
