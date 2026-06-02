"""Tests for the strategy-health statistical-significance layer."""
from app.strategy_health.anomaly_detector import StrategyAnomalyDetector
from app.strategy_health.drift_detector import StrategyDriftDetector
from app.strategy_health.statistical_tests import (
    binomial_winrate_pvalue,
    is_sharpe_significantly_below,
    loss_streak_pvalue,
    sharpe_standard_error,
)


class _Baseline:
    def __init__(self, sharpe, win_rate, pf, dd):
        self.expected_sharpe = sharpe
        self.expected_win_rate = win_rate
        self.expected_profit_factor = pf
        self.expected_drawdown = dd


class _Trade:
    def __init__(self, pnl):
        self.realized_pnl = pnl


def test_binomial_pvalue_flags_significant_drop():
    # 30/100 wins vs a 60% baseline is highly unlikely by chance.
    assert binomial_winrate_pvalue(30, 100, 0.6) < 0.01
    # Observed at/above baseline is never "below".
    assert binomial_winrate_pvalue(60, 100, 0.6) == 1.0
    # A tiny dip on a small sample is not significant.
    assert binomial_winrate_pvalue(58, 100, 0.6) > 0.05


def test_loss_streak_pvalue():
    assert loss_streak_pvalue(3, 0.5) == 0.125
    assert abs(loss_streak_pvalue(4, 0.3) - 0.3**4) < 1e-12


def test_sharpe_significance():
    assert sharpe_standard_error(2.0, 100) > 0
    # Large drop with a big sample is significant; a small drop is not.
    assert is_sharpe_significantly_below(0.5, 2.0, 200) is True
    assert is_sharpe_significantly_below(1.95, 2.0, 200) is False


def test_drift_escalates_only_when_statistically_significant():
    baseline = _Baseline(2.0, 0.60, 2.0, 0.10)
    # A modest win-rate dip (0.60 -> 0.50) does NOT cross the 25% heuristic
    # threshold, so without a sample size the drift stays low...
    live = {"sharpe": 1.9, "win_rate": 0.50, "profit_factor": 1.9, "drawdown": 0.10, "expectancy": 5.0}
    low, _ = StrategyDriftDetector.calculate_drift_score(live, baseline, n_trades=0)
    assert low < 0.55
    # ...but with 200 trades the binomial test finds it significant -> escalates.
    high, details = StrategyDriftDetector.calculate_drift_score(live, baseline, n_trades=200)
    assert high >= 0.55
    assert details["statistical"]["win_rate_significant"] is True


def test_adaptive_loss_streak_for_high_win_rate():
    detector = StrategyAnomalyDetector()
    # 10 wins then a 4-loss streak: ~71% win rate, a 4-run is improbable
    # (0.286**4 ~ 0.007 < 0.01), so it is flagged even though it is under 6.
    trades = [_Trade(10.0)] * 10 + [_Trade(-10.0)] * 4
    is_anom, reason = detector.detect_anomalies(trades)
    assert is_anom
    assert "loss_streak" in reason


def test_normal_loss_streak_not_flagged_at_coinflip_winrate():
    detector = StrategyAnomalyDetector()
    # ~50% win rate: a 4-loss run (p=0.0625) is ordinary and must NOT flag.
    trades = [_Trade(10.0)] * 5 + [_Trade(-10.0)] * 4
    is_anom, reason = detector.detect_anomalies(trades)
    assert not is_anom or reason == "isolation_forest_anomaly_detected"
