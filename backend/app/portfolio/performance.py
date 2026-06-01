import math
from decimal import Decimal
from typing import List, Any


class PerformanceCalculator:
    @staticmethod
    def calculate_win_rate(trades: List[Any]) -> float:
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if float(getattr(t, "realized_pnl", 0.0) or getattr(t, "pnl", 0.0) or t.get("realized_pnl", 0.0) or t.get("pnl", 0.0)) > 0)
        return wins / len(trades)

    @staticmethod
    def calculate_profit_factor(trades: List[Any]) -> float:
        gross_profit = 0.0
        gross_loss = 0.0
        
        for t in trades:
            pnl = float(getattr(t, "realized_pnl", 0.0) or getattr(t, "pnl", 0.0) or t.get("realized_pnl", 0.0) or t.get("pnl", 0.0))
            if pnl > 0:
                gross_profit += pnl
            else:
                gross_loss += abs(pnl)

        if gross_loss == 0.0:
            return float(gross_profit) if gross_profit > 0 else 1.0
        return gross_profit / gross_loss

    @staticmethod
    def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0, annualization_factor: float = 365.0) -> float:
        """
        Calculates annualized Sharpe Ratio based on a list of periodic returns (e.g. daily).
        """
        if len(returns) < 5:
            return 0.0
            
        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance)
        
        if std_dev == 0:
            return 0.0
            
        excess_return = avg_return - (risk_free_rate / annualization_factor)
        return (excess_return / std_dev) * math.sqrt(annualization_factor)

    @staticmethod
    def calculate_drawdown(equity_curve: List[float]) -> float:
        """
        Calculates the current drawdown based on the equity curve.
        """
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @staticmethod
    def calculate_stability_score(equity_curve: List[float]) -> float:
        """
        Calculates stability of the equity curve. 
        Higher stability score means the curve is smoother (closer to linear growth).
        Uses R-squared of linear regression or simple variance check.
        """
        n = len(equity_curve)
        if n < 5:
            return 1.0

        # Run a simple linear regression: y = equity_curve, x = index [0...n-1]
        x = list(range(n))
        y = equity_curve

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        den = sum((x[i] - mean_x) ** 2 for i in range(n))

        if den == 0:
            return 1.0

        slope = num / den
        intercept = mean_y - slope * mean_x

        # Calculate R-squared
        y_pred = [slope * xi + intercept for xi in x]
        ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((y[i] - mean_y) ** 2 for i in range(n))

        if ss_tot == 0:
            return 1.0

        r_squared = 1.0 - (ss_res / ss_tot)
        return float(max(0.0, min(1.0, r_squared)))
