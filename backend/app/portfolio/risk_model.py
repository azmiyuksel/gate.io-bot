from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.models.entities import Portfolio, PortfolioMetric


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

    def _period_peak_drawdown(
        self, portfolio_id: int, period_hours: int
    ) -> Decimal | None:
        """Calculate the drawdown from peak equity within a time window.

        Returns the drawdown as a positive fraction (e.g. 0.03 == 3% drawdown)
        or ``None`` if there is insufficient data for the period.
        """
        since = datetime.now(UTC) - timedelta(hours=period_hours)
        rows = (
            self.db.query(PortfolioMetric)
            .filter(PortfolioMetric.portfolio_id == portfolio_id)
            .filter(PortfolioMetric.timestamp >= since)
            .order_by(PortfolioMetric.timestamp.asc())
            .all()
        )
        equities = [float(r.total_equity) for r in rows if r.total_equity]
        if len(equities) < 2:
            return None
        peak = max(equities)
        current = equities[-1]
        if peak <= 0:
            return Decimal("0")
        return Decimal(str(round((peak - current) / peak, 6)))

    def check_risk_limits(self, portfolio: Portfolio) -> Tuple[bool, str]:
        """
        Validates portfolio drawdown/loss limits against the daily, weekly, and
        monthly budgets using time-windowed equity peaks.

        Each period checks drawdown from the peak within its own window,
        rather than using the all-time peak — so the daily limit truly
        represents a 24-hour drawdown budget, not the entire history.
        """
        if portfolio.peak_equity <= 0:
            return True, "valid"

        # Daily: drawdown from peak in last 24h
        daily_dd = self._period_peak_drawdown(portfolio.id, period_hours=24)
        if daily_dd is not None and daily_dd >= portfolio.daily_max_risk_pct:
            return False, f"daily_risk_limit_exceeded (drawdown {daily_dd:.2%})"

        # Weekly: drawdown from peak in last 168h (7 days)
        weekly_dd = self._period_peak_drawdown(portfolio.id, period_hours=168)
        if weekly_dd is not None and weekly_dd >= portfolio.weekly_max_risk_pct:
            return False, f"weekly_risk_limit_exceeded (drawdown {weekly_dd:.2%})"

        # Monthly: drawdown from peak in last 720h (30 days)
        monthly_dd = self._period_peak_drawdown(portfolio.id, period_hours=720)
        if monthly_dd is not None and monthly_dd >= portfolio.monthly_max_risk_pct:
            return False, f"monthly_risk_limit_exceeded (drawdown {monthly_dd:.2%})"

        # Fallback: all-time drawdown
        if portfolio.total_equity < portfolio.peak_equity:
            alltime_dd = (portfolio.peak_equity - portfolio.total_equity) / portfolio.peak_equity
            if alltime_dd >= portfolio.daily_max_risk_pct:
                return False, f"alltime_risk_limit_exceeded (drawdown {alltime_dd:.2%})"

        return True, "valid"

    @staticmethod
    def calculate_position_size(
        equity: Decimal,
        price: Decimal,
        atr: Decimal,
        risk_per_trade_pct: Decimal = Decimal("0.01"),  # 1% standard trade risk
        atr_multiplier: Decimal = Decimal("2.0"),
        side: str = "long",
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Calculates position size and stop-loss based on account equity, ATR, and target risk.

        Args:
            side: "long" or "short" — determines stop-loss direction.

        Returns: (position_size, stop_loss_distance, stop_loss_price)
        """
        if price <= 0 or atr <= 0 or equity <= 0:
            return Decimal("0"), Decimal("0"), Decimal("0")

        stop_loss_distance = atr * atr_multiplier

        # risk_amount = equity * risk_per_trade_pct
        risk_amount = equity * risk_per_trade_pct

        # position_size (quantity) = risk_amount / stop_loss_distance
        quantity = risk_amount / stop_loss_distance

        # stop_loss_price direction depends on position side
        if side == "short":
            stop_loss_price = price + stop_loss_distance
        else:
            stop_loss_price = price - stop_loss_distance

        return quantity, stop_loss_distance, stop_loss_price
