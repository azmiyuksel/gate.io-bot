"""Fitness scoring, ranking and the production-promotion gate."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.strategy_research.models import (
    EvaluationResult,
    PromotionDecision,
    compute_fitness,
)


@dataclass(frozen=True)
class PromotionVerdict:
    decision: PromotionDecision
    passed: bool
    reasons: list[str]


class StrategyEvaluator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def score(self, result: EvaluationResult) -> EvaluationResult:
        result.fitness = compute_fitness(
            sharpe=result.sharpe,
            stability=result.stability_score,
            profit_factor=result.profit_factor,
            max_drawdown=result.max_drawdown,
        )
        return result

    def rank(self, results: list[EvaluationResult]) -> list[EvaluationResult]:
        return sorted(results, key=lambda r: r.fitness, reverse=True)

    def evaluate_promotion(self, result: EvaluationResult) -> PromotionVerdict:
        """Apply the production gate. Any failing condition rejects the strategy."""
        s = self.settings
        reasons: list[str] = []

        if result.overfit:
            reasons.append("overfit detected (OOS Sharpe collapse)")
        if result.sharpe < s.research_min_sharpe:
            reasons.append(f"sharpe {result.sharpe:.2f} < {s.research_min_sharpe}")
        if result.max_drawdown > s.research_max_drawdown:
            reasons.append(f"drawdown {result.max_drawdown:.2f} > {s.research_max_drawdown}")
        if result.stability_score < s.research_min_stability:
            reasons.append(f"stability {result.stability_score:.2f} < {s.research_min_stability}")
        if result.consistency_score < s.research_min_consistency:
            reasons.append(f"consistency {result.consistency_score:.2f} < {s.research_min_consistency}")
        if result.total_trades < s.research_min_trades:
            reasons.append(f"trades {result.total_trades} < {s.research_min_trades}")

        track_days = int(result.metrics.get("track_days", 0))
        if track_days < s.research_min_track_days:
            reasons.append(f"track record {track_days}d < {s.research_min_track_days}d")

        dsr = float(result.metrics.get("dsr_pvalue", 1.0))
        dsr_threshold = 1.0 - s.research_dsr_confidence
        if dsr > dsr_threshold:
            reasons.append(f"DSR p-value {dsr:.4f} > {dsr_threshold:.4f} (not significant at {s.research_dsr_confidence})")

        passed = not reasons
        return PromotionVerdict(
            decision=PromotionDecision.promoted if passed else PromotionDecision.rejected,
            passed=passed,
            reasons=reasons or ["all gate conditions satisfied"],
        )
