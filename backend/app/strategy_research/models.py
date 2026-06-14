"""Domain types for the Strategy Research Lab.

A *genome* is the parameter vector of a strategy template. Templates declare a
search space (per-parameter bounds + type) so the generator, mutation engine and
clustering layer can operate generically. Today one template is registered
(``ema_rsi_atr``, backed by the backtest engine's strategy); new templates can be
registered without touching the generator/evaluator.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class StrategyStatus(StrEnum):
    candidate = "CANDIDATE"
    promoted = "PROMOTED"
    rejected = "REJECTED"
    archived = "ARCHIVED"


class ExperimentType(StrEnum):
    generation = "GENERATION"
    mutation = "MUTATION"
    crossover = "CROSSOVER"
    ab_test = "AB_TEST"
    evaluation = "EVALUATION"


class ExperimentStatus(StrEnum):
    pending = "PENDING"
    running = "RUNNING"
    completed = "COMPLETED"
    failed = "FAILED"


class PromotionDecision(StrEnum):
    promoted = "PROMOTED"
    rejected = "REJECTED"


class HypothesisStatus(StrEnum):
    untested = "UNTESTED"
    supported = "SUPPORTED"
    rejected = "REJECTED"
    inconclusive = "INCONCLUSIVE"


class FeatureCategory(StrEnum):
    price = "PRICE"
    volume = "VOLUME"
    volatility = "VOLATILITY"
    trend = "TREND"
    order_flow = "ORDER_FLOW"


# ---------------------------------------------------------------------------
# Search space
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParamSpec:
    name: str
    low: float
    high: float
    is_int: bool = False
    step: float | None = None

    def sample(self, rng: random.Random) -> float | int:
        if self.is_int:
            return rng.randint(int(self.low), int(self.high))
        value = rng.uniform(self.low, self.high)
        return round(value, 6)

    def clamp(self, value: float) -> float | int:
        value = max(self.low, min(self.high, value))
        return int(round(value)) if self.is_int else round(value, 6)


@dataclass(frozen=True)
class StrategyTemplate:
    name: str
    indicators: tuple[str, ...]
    params: tuple[ParamSpec, ...]

    def spec(self, name: str) -> ParamSpec | None:
        return next((p for p in self.params if p.name == name), None)

    def default_genome(self, rng: random.Random) -> dict[str, Any]:
        return {p.name: p.sample(rng) for p in self.params}


# The parameter family the backtest engine's EmaRsiAtrStrategy understands.
EMA_RSI_ATR_TEMPLATE = StrategyTemplate(
    name="ema_rsi_atr",
    indicators=("EMA", "RSI", "ATR"),
    params=(
        ParamSpec("ema_trend", 100, 300, is_int=True),
        ParamSpec("ema_entry", 10, 60, is_int=True),
        ParamSpec("rsi_period", 7, 21, is_int=True),
        ParamSpec("rsi_threshold", 20, 45),
        ParamSpec("atr_period", 7, 21, is_int=True),
        ParamSpec("atr_multiplier", 1.0, 3.0),
        ParamSpec("reward_risk", 1.5, 3.5),
        ParamSpec("max_capital_per_trade_pct", 0.005, 0.02),
        ParamSpec("trailing_stop_pct", 0.005, 0.03),
    ),
)

MACD_TEMPLATE = StrategyTemplate(
    name="macd",
    indicators=("MACD", "ATR"),
    params=(
        ParamSpec("macd_fast", 8, 16, is_int=True),
        ParamSpec("macd_slow", 20, 34, is_int=True),
        ParamSpec("macd_signal", 6, 12, is_int=True),
        ParamSpec("atr_period", 7, 21, is_int=True),
        ParamSpec("atr_multiplier", 1.0, 3.0),
        ParamSpec("reward_risk", 1.5, 3.5),
        ParamSpec("max_capital_per_trade_pct", 0.005, 0.02),
        ParamSpec("trailing_stop_pct", 0.005, 0.03),
    ),
)

BOLLINGER_BANDS_TEMPLATE = StrategyTemplate(
    name="bollinger_bands",
    indicators=("BB", "RSI", "ATR"),
    params=(
        ParamSpec("bb_period", 10, 30, is_int=True),
        ParamSpec("bb_std", 1.5, 3.0),
        ParamSpec("rsi_period", 7, 21, is_int=True),
        ParamSpec("rsi_oversold", 25, 45),
        ParamSpec("atr_period", 7, 21, is_int=True),
        ParamSpec("atr_multiplier", 1.0, 3.0),
        ParamSpec("reward_risk", 1.5, 3.5),
        ParamSpec("max_capital_per_trade_pct", 0.005, 0.02),
        ParamSpec("trailing_stop_pct", 0.005, 0.03),
    ),
)

TEMPLATES: dict[str, StrategyTemplate] = {
    EMA_RSI_ATR_TEMPLATE.name: EMA_RSI_ATR_TEMPLATE,
    MACD_TEMPLATE.name: MACD_TEMPLATE,
    BOLLINGER_BANDS_TEMPLATE.name: BOLLINGER_BANDS_TEMPLATE,
}


def get_template(name: str) -> StrategyTemplate:
    if name not in TEMPLATES:
        raise ValueError(f"Unknown strategy template: {name}")
    return TEMPLATES[name]


# ---------------------------------------------------------------------------
# Genome + evaluation results
# ---------------------------------------------------------------------------
@dataclass
class StrategyGenome:
    template: str
    parameters: dict[str, Any]
    origin: str = "generated"  # generated | mutated | crossover | seed
    parent_ids: list[int] = field(default_factory=list)

    def signature(self) -> str:
        """Stable string for dedup/labelling."""
        items = sorted(self.parameters.items())
        return self.template + "|" + ",".join(f"{k}={v}" for k, v in items)


@dataclass
class WalkForwardWindowResult:
    index: int
    sharpe: float
    total_return: float
    max_drawdown: float
    trades: int


@dataclass
class EvaluationResult:
    genome: StrategyGenome
    metrics: dict[str, Any]
    monte_carlo: dict[str, Any]
    walk_forward: list[WalkForwardWindowResult]
    sharpe: float
    profit_factor: float
    max_drawdown: float          # positive magnitude (0..1)
    stability_score: float        # 0..1 equity-curve R^2
    consistency_score: float      # 0..1 fraction of profitable WF windows
    in_sample_sharpe: float
    out_sample_sharpe: float
    overfit: bool
    total_trades: int
    fitness: float = 0.0


# ---------------------------------------------------------------------------
# Fitness
# ---------------------------------------------------------------------------
# fitness = 0.4*sharpe + 0.3*stability + 0.2*profit_factor - 0.1*drawdown
FITNESS_SHARPE_WEIGHT = 0.40
FITNESS_STABILITY_WEIGHT = 0.30
FITNESS_PROFIT_FACTOR_WEIGHT = 0.20
FITNESS_DRAWDOWN_WEIGHT = 0.10


def compute_fitness(
    *, sharpe: float, stability: float, profit_factor: float, max_drawdown: float
) -> float:
    """max_drawdown is a positive magnitude (0..1)."""
    # Bound profit_factor so a single huge value cannot dominate.
    pf = max(0.0, min(profit_factor, 5.0))
    return round(
        FITNESS_SHARPE_WEIGHT * sharpe
        + FITNESS_STABILITY_WEIGHT * stability
        + FITNESS_PROFIT_FACTOR_WEIGHT * pf
        - FITNESS_DRAWDOWN_WEIGHT * abs(max_drawdown) * 10.0,
        6,
    )
