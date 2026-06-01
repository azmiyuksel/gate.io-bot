from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.entities import StrategyBaseline


class StrategyBaselineManager:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_baseline(self, strategy_name: str) -> StrategyBaseline:
        """
        Retrieves the baseline profile for a strategy, creating defaults if not found.
        """
        baseline = self.db.query(StrategyBaseline).filter(StrategyBaseline.strategy_name == strategy_name).first()
        if not baseline:
            baseline = StrategyBaseline(
                strategy_name=strategy_name,
                expected_sharpe=Decimal("1.80"),
                expected_win_rate=Decimal("0.58"),
                expected_profit_factor=Decimal("1.80"),
                expected_drawdown=Decimal("0.12"),
                expected_trade_frequency=Decimal("5.0")
            )
            self.db.add(baseline)
            self.db.commit()
            self.db.refresh(baseline)
        return baseline

    def update_baseline(self, strategy_name: str, metrics: dict) -> StrategyBaseline:
        """
        Updates the baseline expected metrics for a strategy (e.g. after optimization or walk-forward runs).
        """
        baseline = self.get_or_create_baseline(strategy_name)
        baseline.expected_sharpe = Decimal(str(metrics.get("sharpe", baseline.expected_sharpe)))
        baseline.expected_win_rate = Decimal(str(metrics.get("win_rate", baseline.expected_win_rate)))
        baseline.expected_profit_factor = Decimal(str(metrics.get("profit_factor", baseline.expected_profit_factor)))
        baseline.expected_drawdown = Decimal(str(metrics.get("drawdown", baseline.expected_drawdown)))
        baseline.expected_trade_frequency = Decimal(str(metrics.get("trade_frequency", baseline.expected_trade_frequency)))
        self.db.commit()
        self.db.refresh(baseline)
        return baseline

