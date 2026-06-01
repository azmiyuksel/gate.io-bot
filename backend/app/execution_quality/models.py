from enum import StrEnum


class SlippageCategory(StrEnum):
    good = "GOOD"          # < 0.05%
    normal = "NORMAL"      # 0.05% - 0.2%
    bad = "BAD"            # 0.2% - 0.5%
    critical = "CRITICAL"  # > 0.5%


class ExecutionQualityCategory(StrEnum):
    excellent = "Excellent"    # 90 - 100
    good = "Good"              # 75 - 89
    acceptable = "Acceptable"  # 50 - 74
    poor = "Poor"              # < 50


# Core Execution Score Weights
SLIPPAGE_WEIGHT = 0.40
FILL_QUALITY_WEIGHT = 0.30
LATENCY_WEIGHT = 0.20
CONSISTENCY_WEIGHT = 0.10

# Fill Quality Score Weights
FILL_PRICE_ACCURACY_WEIGHT = 0.40
FILL_COMPLETION_WEIGHT = 0.30
FILL_SPEED_WEIGHT = 0.20
FILL_CONSISTENCY_WEIGHT = 0.10
