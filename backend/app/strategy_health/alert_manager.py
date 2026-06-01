from typing import Tuple
from sqlalchemy.orm import Session
from app.models.entities import StrategyAlert
from app.models.enums import StrategyAlertLevel
from app.strategy_health.models import DRIFT_CRITICAL_THRESHOLD, DRIFT_WARNING_THRESHOLD


class StrategyAlertManager:
    def __init__(self, db: Session) -> None:
        self.db = db

    def evaluate_alert(self, strategy_name: str, drift_score: float, is_anomalous: bool, message: str) -> Tuple[StrategyAlertLevel, str]:
        """
        Determines the alert level and the corrective action based on drift and anomalies.
        Logs the alert in the database.
        """
        level = StrategyAlertLevel.green
        action = "none"

        if drift_score >= DRIFT_CRITICAL_THRESHOLD or is_anomalous:
            level = StrategyAlertLevel.red
            action = "pause_strategy"
        elif drift_score >= DRIFT_WARNING_THRESHOLD:
            level = StrategyAlertLevel.orange
            action = "block_new_trades"
        elif drift_score >= 0.3:
            level = StrategyAlertLevel.yellow
            action = "risk_reduced_50"

        # Log to DB
        alert = StrategyAlert(
            strategy_name=strategy_name,
            alert_level=level,
            message=message,
            action_taken=action
        )
        self.db.add(alert)
        self.db.commit()

        return level, action
