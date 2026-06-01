from decimal import Decimal


class StrategyRiskAdjuster:
    @staticmethod
    def get_risk_multiplier(drift_score: float) -> Decimal:
        """
        Determines the position sizing risk multiplier based on performance drift:
        - 0.0 to 0.3 -> 1.0 (No adjustment)
        - 0.3 to 0.5 -> 0.7 (Light caution)
        - 0.5 to 0.7 -> 0.4 (Heavy caution)
        - > 0.7 -> 0.0 (Strategy paused)
        """
        if drift_score <= 0.3:
            return Decimal("1.0")
        elif drift_score <= 0.5:
            return Decimal("0.7")
        elif drift_score <= 0.7:
            return Decimal("0.4")
        else:
            return Decimal("0.0")
