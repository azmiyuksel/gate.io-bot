from decimal import Decimal
from typing import Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.models.entities import Portfolio


class PortfolioRiskModel:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def historical_var_cvar(equity_history: list[float], confidence: float = 0.95) -> dict:
        """Historical Value-at-Risk and Conditional VaR (expected shortfall).

        VaR_95 is the loss at the 5th percentile of the return distribution;
        CVaR_95 is the mean loss in that tail. Returned as positive fractions
        (e.g. 0.04 == a 4% loss). Needs at least a few return observations.
        """
        if not equity_history or len(equity_history) < 3:
            return {"var": 0.0, "cvar": 0.0}
        equity = np.array(equity_history, dtype="float64")
        returns = np.diff(equity) / equity[:-1]
        returns = returns[np.isfinite(returns)]
        if returns.size == 0:
            return {"var": 0.0, "cvar": 0.0}
        alpha = (1 - confidence) * 100
        var_threshold = np.percentile(returns, alpha)  # negative for a loss
        tail = returns[returns <= var_threshold]
        cvar = tail.mean() if tail.size else var_threshold
        # Report losses as positive magnitudes.
        return {"var": float(max(-var_threshold, 0.0)), "cvar": float(max(-cvar, 0.0))}

    def check_risk_limits(self, portfolio: Portfolio) -> Tuple[bool, str]:
        """
        Validates portfolio drawdown/loss limits against the daily, weekly, and monthly budgets.
        Drawdown is calculated from peak_equity (peak-to-trough), not vs cash_balance.
        """
        if portfolio.peak_equity <= 0:
            return True, "valid"

        drawdown_pct = Decimal("0")
        if portfolio.total_equity < portfolio.peak_equity:
            drawdown_pct = (portfolio.peak_equity - portfolio.total_equity) / portfolio.peak_equity

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
