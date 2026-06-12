from decimal import Decimal

from app.core.config import get_settings


class StrategyRiskAdjuster:
    @staticmethod
    def get_risk_multiplier(drift_score: float) -> Decimal:
        """
        Determines the position sizing risk multiplier based on performance drift.
        Tiers are configurable via Settings.
        """
        s = get_settings()
        if drift_score <= s.health_drift_tier_low:
            return Decimal(str(s.health_risk_mult_low))
        elif drift_score <= s.health_drift_tier_mid:
            return Decimal(str(s.health_risk_mult_mid))
        elif drift_score <= s.health_drift_tier_high:
            return Decimal(str(s.health_risk_mult_high))
        else:
            return Decimal(str(s.health_risk_mult_paused))
