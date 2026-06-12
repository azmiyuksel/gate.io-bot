import logging
from decimal import Decimal
from typing import List, Any
from sqlalchemy.orm import Session

from app.models.entities import (
    StrategyDriftScore,
    StrategyHealthLog,
    StrategySettings,
    StrategyStateHistory,
    Trade,
)
from app.models.enums import StrategyHealthState
from app.strategy_health.alert_manager import StrategyAlertManager
from app.strategy_health.anomaly_detector import StrategyAnomalyDetector
from app.strategy_health.baseline import StrategyBaselineManager
from app.strategy_health.drift_detector import StrategyDriftDetector
from app.strategy_health.metrics_tracker import StrategyMetricsTracker
from app.strategy_health.models import MIN_TRADE_WARMUP
from app.strategy_health.performance_analyzer import StrategyPerformanceAnalyzer
from app.strategy_health.risk_adjuster import StrategyRiskAdjuster
from app.services.notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class StrategyHealthEngine:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.baseline_manager = StrategyBaselineManager(db)
        self.drift_detector = StrategyDriftDetector()
        self.anomaly_detector = StrategyAnomalyDetector()
        self.alert_manager = StrategyAlertManager(db)
        self.notifier = TelegramNotifier()

    def update_health(self, strategy_name: str, trades_list: List[Any] = None, current_regime: str = "SIDEWAYS") -> dict:
        """
        Calculates strategy health, handles state transitions, updates risk multipliers,
        persists metrics, and dispatches alarms.
        """
        # 1. Fetch trades from DB if not provided
        if trades_list is None:
            trades_list = (
                self.db.query(Trade)
                .filter(Trade.strategy_name == strategy_name)
                .order_by(Trade.traded_at.asc())
                .all()
            )

        baseline = self.baseline_manager.get_or_create_baseline(strategy_name)

        if len(trades_list) < MIN_TRADE_WARMUP:
            # Under warm-up phase, return default healthy score
            return {
                "health_score": 100.0,
                "drift_score": 0.0,
                "state": StrategyHealthState.active,
                "risk_multiplier": Decimal("1.0"),
                "reason": "warmup_period"
            }

        # 2. Compute rolling performance metrics
        live_metrics = StrategyMetricsTracker.calculate_rolling_metrics(trades_list)

        # 3. Calculate drift (with statistical-significance gating on the sample).
        drift_score, drift_details = self.drift_detector.calculate_drift_score(
            live_metrics, baseline, n_trades=len(trades_list)
        )

        # 4. Check anomalies
        is_anomalous, anomaly_reason = self.anomaly_detector.detect_anomalies(trades_list)

        # 5. Diagnose failure mode
        failure_mode, failure_details = StrategyPerformanceAnalyzer.analyze_failure_mode(
            live_metrics,
            baseline,
            trades_list,
            current_regime
        )

        # 6. Evaluate alerts
        alert_msg = f"Health check: drift={drift_score:.2f}, anomaly={anomaly_reason}, failure={failure_mode}"
        alert_level, action = self.alert_manager.evaluate_alert(strategy_name, drift_score, is_anomalous, alert_msg)

        # 7. Lifecycle state transitions
        current_state = self._get_current_state(strategy_name)
        new_state = current_state

        if action == "pause_strategy":
            new_state = StrategyHealthState.paused
            # De-authorize strategy execution in the db
            settings = self.db.query(StrategySettings).filter(StrategySettings.name == strategy_name).first()
            if settings and settings.is_enabled:
                settings.is_enabled = False
                self.db.commit()
                # Send critical alert
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.notifier.send_strategy_paused(
                        strategy_name,
                        f"performansı kritik seviyede bozuldu (drift={drift_score:.2f})",
                    ))
                except RuntimeError:
                    logger.warning("Strategy-health alert skipped (no running event loop)", exc_info=True)
        elif action == "block_new_trades":
            new_state = StrategyHealthState.degraded
        elif action == "risk_reduced_50":
            new_state = StrategyHealthState.degraded
        else:
            new_state = StrategyHealthState.active

        if new_state != current_state:
            self._log_state_transition(strategy_name, current_state, new_state, alert_msg)

        # 8. Risk Adjuster
        risk_multiplier = StrategyRiskAdjuster.get_risk_multiplier(drift_score)

        # 9. Record metric history
        health_score = max(0.0, 100.0 - (drift_score * 100.0))
        
        log = StrategyHealthLog(
            strategy_name=strategy_name,
            rolling_sharpe=Decimal(str(live_metrics["sharpe"])),
            rolling_win_rate=Decimal(str(live_metrics["win_rate"])),
            rolling_profit_factor=Decimal(str(live_metrics["profit_factor"])),
            rolling_drawdown=Decimal(str(live_metrics["drawdown"])),
            expectancy=Decimal(str(live_metrics["expectancy"])),
            health_score=Decimal(str(health_score))
        )
        self.db.add(log)

        drift_record = StrategyDriftScore(
            strategy_name=strategy_name,
            drift_score=Decimal(str(drift_score)),
            deviation_details=drift_details
        )
        self.db.add(drift_record)
        self.db.commit()

        return {
            "health_score": health_score,
            "drift_score": drift_score,
            "state": new_state,
            "risk_multiplier": risk_multiplier,
            "failure_mode": failure_mode,
            "anomaly": anomaly_reason
        }

    def _get_current_state(self, strategy_name: str) -> StrategyHealthState:
        last_transition = (
            self.db.query(StrategyStateHistory)
            .filter(StrategyStateHistory.strategy_name == strategy_name)
            .order_by(StrategyStateHistory.created_at.desc())
            .first()
        )
        return last_transition.new_state if last_transition else StrategyHealthState.active

    def _log_state_transition(
        self,
        strategy_name: str,
        old_state: StrategyHealthState,
        new_state: StrategyHealthState,
        reason: str
    ) -> None:
        transition = StrategyStateHistory(
            strategy_name=strategy_name,
            old_state=old_state,
            new_state=new_state,
            trigger_reason=reason
        )
        self.db.add(transition)
        self.db.commit()
