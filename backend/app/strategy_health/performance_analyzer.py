from decimal import Decimal
from typing import List, Any
from app.models.enums import MarketRegimeType
from app.strategy_health.models import StrategyFailureMode


class StrategyPerformanceAnalyzer:
    @staticmethod
    def analyze_failure_mode(
        live: dict,
        baseline: Any,
        trades: List[Any],
        current_regime: str
    ) -> tuple[str, str]:
        """
        Diagnoses strategy performance failures and assigns a Failure Mode.
        Returns: (StrategyFailureMode, diagnosis_details)
        """
        if len(trades) < 5:
            return StrategyFailureMode.healthy, "Not enough trades to analyze failure modes"

        live_sharpe = live["sharpe"]
        live_win_rate = live["win_rate"]
        live_dd = live["drawdown"]
        base_win_rate = float(baseline.expected_win_rate)
        base_dd = float(baseline.expected_drawdown)

        # 1. Sudden Collapse: drawdown is more than double the expected max drawdown
        if live_dd > base_dd * 2.0:
            return StrategyFailureMode.sudden_collapse, f"Drawdown ({live_dd:.1%}) is more than double baseline expected drawdown ({base_dd:.1%})"

        # 2. Volatility Mismatch: high losses in highly volatile regimes
        # If current regime is HIGH_VOLATILITY and latest trade is a loss
        if current_regime == "HIGH_VOLATILITY" and live_win_rate < base_win_rate * 0.70:
            return StrategyFailureMode.volatility_mismatch, "Strategy is suffering high loss rates during a high-volatility market phase"

        # 3. Regime Mismatch: strategy is running in incompatible regimes
        # Mean reversion in trends or trend following in ranges
        if current_regime in ("TRENDING_BULL", "TRENDING_BEAR") and live_win_rate < base_win_rate * 0.75:
            return StrategyFailureMode.regime_mismatch, f"Strategy underperforming in trending regime ({current_regime})"
        elif current_regime == "SIDEWAYS" and live_win_rate < base_win_rate * 0.75:
            return StrategyFailureMode.regime_mismatch, "Strategy underperforming in range/sideways market regime"

        # 4. Gradual Decay: slowly declining win rate or profit factor
        if live_sharpe < float(baseline.expected_sharpe) * 0.60:
            return StrategyFailureMode.gradual_decay, f"Rolling Sharpe ({live_sharpe:.2f}) has drifted below 60% of expected baseline ({float(baseline.expected_sharpe):.2f})"

        return StrategyFailureMode.healthy, "Strategy performance is within healthy limits"
