"""Domain types for the Auto Learning & Continuous Evolution System.

Core principle encoded here: nothing reaches production automatically. The
promotion state machine always terminates at a human decision
(``awaiting_approval`` -> ``approved`` / ``rejected``). The ``SAFETY_INVARIANTS``
list documents the hard restrictions the engine must never violate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class LearningCycleStatus(StrEnum):
    running = "RUNNING"
    completed = "COMPLETED"
    failed = "FAILED"
    stopped = "STOPPED"


class PromotionRequestStatus(StrEnum):
    awaiting_validation = "AWAITING_VALIDATION"
    validation_failed = "VALIDATION_FAILED"
    awaiting_paper = "AWAITING_PAPER"
    paper_failed = "PAPER_FAILED"
    awaiting_approval = "AWAITING_APPROVAL"
    approved = "APPROVED"
    rejected = "REJECTED"


class KnowledgeType(StrEnum):
    pattern = "PATTERN"
    failure = "FAILURE"
    regime = "REGIME"
    portfolio = "PORTFOLIO"
    feature = "FEATURE"
    meta = "META"


class ValidationStage(StrEnum):
    backtest = "BACKTEST"
    cross_validation = "CROSS_VALIDATION"
    walk_forward = "WALK_FORWARD"
    monte_carlo = "MONTE_CARLO"
    robustness = "ROBUSTNESS"
    paper = "PAPER_TRADING"


# ---------------------------------------------------------------------------
# Safety - hard invariants the auto-learning layer must never break.
# These are asserted by SafetyGuard and covered by a test.
# ---------------------------------------------------------------------------
SAFETY_INVARIANTS = (
    "never enable live trading without human approval",
    "never modify risk limits",
    "never disable or reset the circuit breaker / kill switch",
    "never deploy a strategy to production automatically",
)


# ---------------------------------------------------------------------------
# Ranking: 30 robustness + 25 walk-forward + 20 stability + 15 sharpe + 10 dd
# ---------------------------------------------------------------------------
RANK_ROBUSTNESS_WEIGHT = 30.0
RANK_WALK_FORWARD_WEIGHT = 25.0
RANK_STABILITY_WEIGHT = 20.0
RANK_SHARPE_WEIGHT = 15.0
RANK_DRAWDOWN_WEIGHT = 10.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass
class RankingBreakdown:
    robustness: float
    walk_forward: float
    stability: float
    sharpe: float
    drawdown: float
    total: float


def compute_ranking(
    *,
    sharpe: float,
    stability: float,
    consistency: float,       # walk-forward consistency 0..1
    max_drawdown: float,      # positive magnitude 0..1
    ruin_probability: float,  # monte-carlo 0..1
    overfit: bool,
) -> RankingBreakdown:
    robustness = _clamp01(1.0 - ruin_probability) * (0.0 if overfit else 1.0)
    walk_forward = _clamp01(consistency)
    stability_c = _clamp01(stability)
    sharpe_c = _clamp01(sharpe / 3.0)
    drawdown_c = _clamp01(1.0 - max_drawdown / 0.30)
    total = (
        RANK_ROBUSTNESS_WEIGHT * robustness
        + RANK_WALK_FORWARD_WEIGHT * walk_forward
        + RANK_STABILITY_WEIGHT * stability_c
        + RANK_SHARPE_WEIGHT * sharpe_c
        + RANK_DRAWDOWN_WEIGHT * drawdown_c
    )
    return RankingBreakdown(
        robustness=round(RANK_ROBUSTNESS_WEIGHT * robustness, 4),
        walk_forward=round(RANK_WALK_FORWARD_WEIGHT * walk_forward, 4),
        stability=round(RANK_STABILITY_WEIGHT * stability_c, 4),
        sharpe=round(RANK_SHARPE_WEIGHT * sharpe_c, 4),
        drawdown=round(RANK_DRAWDOWN_WEIGHT * drawdown_c, 4),
        total=round(total, 4),
    )


# ---------------------------------------------------------------------------
# Promotion gate (spec section 9). Human approval is a separate, final step.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PromotionGateThresholds:
    min_sharpe: float = 1.5
    min_profit_factor: float = 1.3
    min_consistency: float = 0.60
    max_ruin_probability: float = 0.20  # Monte Carlo pass


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation pipeline result
# ---------------------------------------------------------------------------
@dataclass
class StageResult:
    stage: ValidationStage
    passed: bool
    detail: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationOutcome:
    passed: bool
    stages: list[StageResult]
    sharpe: float
    profit_factor: float
    consistency: float
    stability: float
    max_drawdown: float
    ruin_probability: float
    overfit: bool
    ranking_total: float
    parameters: dict[str, Any]


@dataclass
class PatternFinding:
    title: str
    description: str
    support: int           # number of trades/observations behind it
    win_rate: float
    avg_pnl: float
    regime: str | None = None


@dataclass
class DiscoveredFeatureSpec:
    name: str
    formula: str
    correlation_with_profit: float
    importance: float
    stability: float
