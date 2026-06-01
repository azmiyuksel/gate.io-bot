from decimal import Decimal
from typing import Tuple, Dict, Any
from sqlalchemy.orm import Session

from app.models.entities import Portfolio, PortfolioAsset


class PortfolioRiskModel:
    def __init__(self, db: Session) -> None:
        self.db = db

    def check_risk_limits(self, portfolio: Portfolio) -> Tuple[bool, str]:
        """
        Validates portfolio drawdown/loss limits against the daily, weekly, and monthly budgets.
        """
        initial = portfolio.total_equity + abs(portfolio.cash_balance - portfolio.total_equity) # Fallback to equity baseline
        if initial <= 0:
            return True, "valid"

        # Check peak-to-trough drawdown or simple losses
        # Here we check limits against the metrics. If limits are exceeded, flag it.
        # Check portfolio metrics (e.g. from the last day/week/month metric points)
        # For simplicity and robust real-time checks, we look at equity vs starting targets
        drawdown_pct = Decimal("0")
        if portfolio.total_equity < portfolio.cash_balance:
            drawdown_pct = (portfolio.cash_balance - portfolio.total_equity) / portfolio.cash_balance

        if drawdown_pct >= portfolio.daily_max_risk_pct:
            return False, f"daily_risk_limit_exceeded (drawdown {drawdown_pct:.2%})"

        if drawdown_pct >= portfolio.weekly_max_risk_pct:
            return False, f"weekly_risk_limit_exceeded (drawdown {drawdown_pct:.2%})"

        if drawdown_pct >= portfolio.monthly_max_risk_pct:
            return False, f"monthly_risk_limit_exceeded (drawdown {drawdown_pct:.2%})"

        return True, "valid"

    @staticmethod
    def calculate_position_size(
        equity: Decimal,
        price: Decimal,
        atr: Decimal,
        risk_per_trade_pct: Decimal = Decimal("0.01"),  # 1% standard trade risk
        atr_multiplier: Decimal = Decimal("2.0")
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Calculates position size and stop-loss based on account equity, ATR, and target risk.
        Returns: (position_size, stop_loss_distance, stop_loss_price)
        """
        if price <= 0 or atr <= 0 or equity <= 0:
            return Decimal("0"), Decimal("0"), Decimal("0")

        stop_loss_distance = atr * atr_multiplier
        
        # risk_amount = equity * risk_per_trade_pct
        risk_amount = equity * risk_per_trade_pct
        
        # position_size (quantity) = risk_amount / stop_loss_distance
        quantity = risk_amount / stop_loss_distance
        
        # stop_loss_price (for buy/long) = price - stop_loss_distance
        stop_loss_price = price - stop_loss_distance
        
        return quantity, stop_loss_distance, stop_loss_price
