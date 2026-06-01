from decimal import Decimal
from app.models.enums import MarketRegimeType

# Ensemble voting weights
WEIGHT_RULE_BASED = 0.4
WEIGHT_CLUSTERING = 0.3
WEIGHT_ML = 0.3

# Regime-specific risk multipliers
RISK_MULTIPLIERS = {
    MarketRegimeType.trending_bull: Decimal("1.0"),
    MarketRegimeType.trending_bear: Decimal("1.0"),  # Or short-only / hedge mode
    MarketRegimeType.sideways: Decimal("0.7"),
    MarketRegimeType.high_volatility: Decimal("0.5"),
    MarketRegimeType.low_volatility: Decimal("1.2"),
    MarketRegimeType.breakout_phase: Decimal("1.1"),
}
