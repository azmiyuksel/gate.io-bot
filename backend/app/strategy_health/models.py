from decimal import Decimal

# Thresholds for strategy drift (decay detection)
DRIFT_WARNING_THRESHOLD = 0.5
DRIFT_CRITICAL_THRESHOLD = 0.7

# Minimum trade counts required before calculating health metrics
MIN_TRADE_WARMUP = 10

# Failure modes
class StrategyFailureMode:
    gradual_decay = "GRADUAL_DECAY"
    sudden_collapse = "SUDDEN_COLLAPSE"
    volatility_mismatch = "VOLATILITY_MISMATCH"
    regime_mismatch = "REGIME_MISMATCH"
    healthy = "HEALTHY"
