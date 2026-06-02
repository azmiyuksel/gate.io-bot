from typing import Any, Dict, Tuple

from app.strategy_health.statistical_tests import (
    binomial_winrate_pvalue,
    is_sharpe_significantly_below,
)

# Minimum live trades before a degradation can be judged statistically.
_MIN_TRADES_FOR_SIGNIFICANCE = 20


class StrategyDriftDetector:
    @staticmethod
    def calculate_drift_score(
        live: Dict[str, float], baseline: Any, n_trades: int = 0
    ) -> Tuple[float, dict]:
        """
        Calculates performance drift (0.0 to 1.0) and lists individual deviations.

        When `n_trades` is provided, a statistical-significance layer (binomial
        test on win rate, standard-error test on Sharpe) distinguishes a real
        degradation from sampling noise and is used to confirm escalation.
        """
        # Convert baseline values to float
        base_sharpe = float(baseline.expected_sharpe)
        base_win_rate = float(baseline.expected_win_rate)
        base_pf = float(baseline.expected_profit_factor)
        base_dd = float(baseline.expected_drawdown)

        live_sharpe = live["sharpe"]
        live_win_rate = live["win_rate"]
        live_pf = live["profit_factor"]
        live_dd = live["drawdown"]
        live_expectancy = live["expectancy"]

        # Calculate deviations (only penalizing underperformance)
        dev_sharpe = max(0.0, (base_sharpe - live_sharpe) / base_sharpe) if base_sharpe > 0 else 0.0
        dev_win_rate = max(0.0, (base_win_rate - live_win_rate) / base_win_rate) if base_win_rate > 0 else 0.0
        dev_pf = max(0.0, (base_pf - live_pf) / base_pf) if base_pf > 0 else 0.0
        dev_dd = max(0.0, (live_dd - base_dd) / base_dd) if base_dd > 0 else 0.0

        # Deviation checklist conditions
        # Sharpe drop > 40%, Win rate drop > 25%, Drawdown increase > 50%
        # Let's compute a weighted average drift score
        # Sharpe weight: 0.35, Win rate: 0.35, Drawdown: 0.20, Profit factor: 0.10
        raw_drift = (
            0.35 * dev_sharpe +
            0.35 * dev_win_rate +
            0.20 * dev_dd +
            0.10 * dev_pf
        )

        # Expectancy check: if expectancy is negative, add severe drift penalty
        if live_expectancy < 0:
            raw_drift = max(raw_drift, 0.75)

        # Threshold triggers
        if dev_sharpe > 0.40 or dev_win_rate > 0.25 or dev_dd > 0.50:
            # Shift drift score to warning/critical bounds
            raw_drift = max(raw_drift, 0.55)

        # Statistical-significance layer (only when we have enough live trades).
        win_rate_pvalue = 1.0
        win_rate_significant = False
        sharpe_significant = False
        if n_trades >= _MIN_TRADES_FOR_SIGNIFICANCE and base_win_rate > 0:
            wins = round(live_win_rate * n_trades)
            win_rate_pvalue = binomial_winrate_pvalue(wins, n_trades, base_win_rate)
            win_rate_significant = win_rate_pvalue < 0.05
            sharpe_significant = is_sharpe_significantly_below(
                live_sharpe, base_sharpe, n_trades
            )
            # A statistically significant drop confirms (escalates) the drift even
            # if the heuristic relative thresholds were not crossed.
            if win_rate_significant or sharpe_significant:
                raw_drift = max(raw_drift, 0.55)

        drift_score = max(0.0, min(1.0, raw_drift))

        details = {
            "deviations": {
                "sharpe": dev_sharpe,
                "win_rate": dev_win_rate,
                "profit_factor": dev_pf,
                "drawdown": dev_dd,
            },
            "statistical": {
                "n_trades": n_trades,
                "win_rate_pvalue": win_rate_pvalue,
                "win_rate_significant": win_rate_significant,
                "sharpe_significant": sharpe_significant,
            },
            "metrics": {
                "live": live,
                "expected": {
                    "sharpe": base_sharpe,
                    "win_rate": base_win_rate,
                    "profit_factor": base_pf,
                    "drawdown": base_dd
                }
            }
        }

        return drift_score, details
