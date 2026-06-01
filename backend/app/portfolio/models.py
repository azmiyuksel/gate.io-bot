from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List


# Default strategy weights
DEFAULT_STRATEGY_WEIGHTS = {
    "EMA Strategy": Decimal("0.40"),
    "RSI Strategy": Decimal("0.30"),
    "Breakout Strategy": Decimal("0.20"),
    "Mean Reversion": Decimal("0.10"),
}


@dataclass
class StrategyPerformance:
    name: str
    sharpe_ratio: Decimal = Decimal("0.0")
    win_rate: Decimal = Decimal("0.0")
    profit_factor: Decimal = Decimal("1.0")
    max_drawdown: Decimal = Decimal("0.0")
    stability_score: Decimal = Decimal("1.0")  # Equity curve stability [0, 1]


@dataclass
class AssetVolatility:
    symbol: str
    atr: Decimal = Decimal("0.0")
    price: Decimal = Decimal("0.0")
    volatility_pct: Decimal = Decimal("0.0")


@dataclass
class CorrelationRisk:
    matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)
    high_correlation_pairs: List[tuple] = field(default_factory=list)
    risk_score: Decimal = Decimal("0.0")  # Combined correlation risk [0, 1]
