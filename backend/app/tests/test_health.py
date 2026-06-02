from decimal import Decimal
from typing import NamedTuple

from app.strategy_health.metrics_tracker import StrategyMetricsTracker
from app.strategy_health.drift_detector import StrategyDriftDetector
from app.strategy_health.anomaly_detector import StrategyAnomalyDetector
from app.strategy_health.risk_adjuster import StrategyRiskAdjuster


class MockTrade(NamedTuple):
    realized_pnl: float


class MockBaseline:
    def __init__(
        self,
        expected_sharpe: float,
        expected_win_rate: float,
        expected_profit_factor: float,
        expected_drawdown: float,
    ) -> None:
        self.expected_sharpe = expected_sharpe
        self.expected_win_rate = expected_win_rate
        self.expected_profit_factor = expected_profit_factor
        self.expected_drawdown = expected_drawdown


def test_metrics_tracker_calculations() -> None:
    # 1. Standard win/loss metrics
    trades = [
        MockTrade(100.0),
        MockTrade(-50.0),
        MockTrade(200.0),
        MockTrade(-100.0),
    ]
    metrics = StrategyMetricsTracker.calculate_rolling_metrics(trades, window=5)

    assert metrics["win_rate"] == 0.5  # 2 wins out of 4 trades
    assert metrics["profit_factor"] == 300.0 / 150.0  # Gross Profit: 300, Gross Loss: 150
    assert metrics["expectancy"] == (150.0 * 0.5) - (75.0 * 0.5)  # (avg_win * wr) - (avg_loss * lr)
    assert metrics["drawdown"] > 0.0

    # 2. Empty list fallback
    empty_metrics = StrategyMetricsTracker.calculate_rolling_metrics([], window=5)
    assert empty_metrics["sharpe"] == 0.0
    assert empty_metrics["win_rate"] == 0.0
    assert empty_metrics["profit_factor"] == 1.0
    assert empty_metrics["drawdown"] == 0.0

    # 3. Winning and losing streaks
    streak_trades = [
        MockTrade(10.0),
        MockTrade(20.0),
        MockTrade(0.0),  # Flat does not count as loss/win, resets streak
        MockTrade(-10.0),
        MockTrade(-20.0),
        MockTrade(-30.0),
        MockTrade(5.0),
    ]
    streaks = StrategyMetricsTracker.calculate_streaks(streak_trades)
    assert streaks["max_win_streak"] == 2
    assert streaks["max_loss_streak"] == 3
    assert streaks["current_win_streak"] == 1
    assert streaks["current_loss_streak"] == 0


def test_drift_detector() -> None:
    # Standard baseline
    baseline = MockBaseline(
        expected_sharpe=2.0,
        expected_win_rate=0.6,
        expected_profit_factor=2.0,
        expected_drawdown=0.1,
    )

    # 1. Normal Performance (Close to baseline)
    live_normal = {
        "sharpe": 2.1,
        "win_rate": 0.62,
        "profit_factor": 2.2,
        "drawdown": 0.08,
        "expectancy": 50.0,
    }
    drift_score, details = StrategyDriftDetector.calculate_drift_score(live_normal, baseline)
    assert drift_score == 0.0
    assert details["deviations"]["sharpe"] == 0.0
    assert details["deviations"]["win_rate"] == 0.0

    # 2. Severe Performance Decay
    live_decay = {
        "sharpe": 0.5,
        "win_rate": 0.35,
        "profit_factor": 0.9,
        "drawdown": 0.25,
        "expectancy": -15.0,
    }
    drift_score_decay, details_decay = StrategyDriftDetector.calculate_drift_score(live_decay, baseline)
    assert drift_score_decay >= 0.55  # Penalty or threshold boost
    assert details_decay["deviations"]["sharpe"] > 0.0
    assert details_decay["deviations"]["win_rate"] > 0.0
    assert details_decay["deviations"]["drawdown"] > 0.0


def test_anomaly_detector() -> None:
    detector = StrategyAnomalyDetector()

    # 1. Insufficient data
    is_anom, reason = detector.detect_anomalies([MockTrade(10.0)] * 4)
    assert not is_anom
    assert reason == "insufficient_data"

    # 2. Consecutive losses streak anomaly
    loss_streak_trades = [MockTrade(-10.0)] * 6
    is_anom_streak, reason_streak = detector.detect_anomalies(loss_streak_trades)
    assert is_anom_streak
    assert "consecutive losses" in reason_streak

    # 3. Z-score extreme loss anomaly
    z_trades = [MockTrade(10.0)] * 10 + [MockTrade(-150.0)]
    is_anom_z, reason_z = detector.detect_anomalies(z_trades)
    assert is_anom_z
    assert "extreme_loss_anomaly" in reason_z

    # 4. Normal trades
    normal_trades = [MockTrade(10.0), MockTrade(-5.0)] * 12
    is_anom_norm, reason_norm = detector.detect_anomalies(normal_trades)
    # Could be normal or fit depending on IsolationForest, but should not trigger Z-score or streak
    assert not is_anom_norm or reason_norm == "isolation_forest_anomaly_detected"


def test_risk_adjuster() -> None:
    assert StrategyRiskAdjuster.get_risk_multiplier(0.1) == Decimal("1.0")
    assert StrategyRiskAdjuster.get_risk_multiplier(0.3) == Decimal("1.0")
    assert StrategyRiskAdjuster.get_risk_multiplier(0.4) == Decimal("0.7")
    assert StrategyRiskAdjuster.get_risk_multiplier(0.6) == Decimal("0.4")
    assert StrategyRiskAdjuster.get_risk_multiplier(0.8) == Decimal("0.0")
