"""Multi-stage validation pipeline.

Every candidate must clear: backtest -> cross-validation -> walk-forward ->
Monte Carlo -> robustness -> paper trading. Reuses the research backtest runner
(identical execution semantics to production). The paper-trading stage uses the
held-out out-of-sample segment as a forward proxy; a *real* paper run plus human
approval are still required before anything is considered for production.
"""
from __future__ import annotations

from app.auto_learning.models import (
    GateResult,
    PromotionGateThresholds,
    StageResult,
    ValidationOutcome,
    ValidationStage,
    compute_ranking,
)
from app.core.config import get_settings
from app.strategy_research.backtest_runner import ResearchBacktestRunner
from app.strategy_research.evaluator import StrategyEvaluator
from app.strategy_research.models import EvaluationResult, StrategyGenome
from sqlalchemy.orm import Session


class ValidationPipeline:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.runner = ResearchBacktestRunner(db)
        self.evaluator = StrategyEvaluator(self.settings)
        self.thresholds = PromotionGateThresholds(
            min_sharpe=self.settings.learning_gate_min_sharpe,
            min_profit_factor=self.settings.learning_gate_min_profit_factor,
            min_consistency=self.settings.learning_gate_min_consistency,
            max_ruin_probability=self.settings.learning_gate_max_ruin,
        )

    def validate(
        self, genome: StrategyGenome, symbol: str = "BTC_USDT", timeframe: str = "1h"
    ) -> tuple[ValidationOutcome, EvaluationResult] | None:
        result = self.runner.evaluate(genome, symbol, timeframe, self.settings.research_wf_windows)
        if result is None:
            return None
        self.evaluator.score(result)

        ruin = float(result.monte_carlo.get("ruin_probability", 1.0))
        t = self.thresholds

        stages = [
            StageResult(
                ValidationStage.backtest,
                result.total_trades >= self.settings.research_min_trades,
                f"{result.total_trades} trades, sharpe {result.sharpe:.2f}",
                {"sharpe": result.sharpe, "trades": result.total_trades},
            ),
            StageResult(
                ValidationStage.cross_validation,
                result.consistency_score >= 0.5,
                f"window consistency {result.consistency_score:.2f}",
                {"consistency": result.consistency_score},
            ),
            StageResult(
                ValidationStage.walk_forward,
                result.consistency_score >= t.min_consistency,
                f"WF consistency {result.consistency_score:.2f} vs {t.min_consistency}",
            ),
            StageResult(
                ValidationStage.monte_carlo,
                ruin <= t.max_ruin_probability,
                f"ruin probability {ruin:.2f} vs {t.max_ruin_probability}",
                {"ruin_probability": ruin},
            ),
            StageResult(
                ValidationStage.robustness,
                (not result.overfit) and result.out_sample_sharpe > 0,
                f"overfit={result.overfit}, OOS sharpe {result.out_sample_sharpe:.2f}",
            ),
            StageResult(
                ValidationStage.paper,
                result.out_sample_sharpe > 0,
                f"OOS forward proxy sharpe {result.out_sample_sharpe:.2f} — "
                f"NOT a substitute for real paper trading",
            ),
        ]

        ranking = compute_ranking(
            sharpe=result.sharpe,
            stability=result.stability_score,
            consistency=result.consistency_score,
            max_drawdown=result.max_drawdown,
            ruin_probability=ruin,
            overfit=result.overfit,
        )

        outcome = ValidationOutcome(
            passed=all(s.passed for s in stages),
            stages=stages,
            sharpe=result.sharpe,
            profit_factor=result.profit_factor,
            consistency=result.consistency_score,
            stability=result.stability_score,
            max_drawdown=result.max_drawdown,
            ruin_probability=ruin,
            overfit=result.overfit,
            ranking_total=ranking.total,
            parameters=genome.parameters,
        )
        return outcome, result

    def gate(self, outcome: ValidationOutcome) -> GateResult:
        """Section 9 promotion gate. Human approval is still required afterwards."""
        t = self.thresholds
        reasons: list[str] = []
        if outcome.sharpe < t.min_sharpe:
            reasons.append(f"sharpe {outcome.sharpe:.2f} < {t.min_sharpe}")
        if outcome.profit_factor < t.min_profit_factor:
            reasons.append(f"profit factor {outcome.profit_factor:.2f} < {t.min_profit_factor}")
        if outcome.consistency < t.min_consistency:
            reasons.append(f"consistency {outcome.consistency:.2f} < {t.min_consistency}")
        if outcome.ruin_probability > t.max_ruin_probability:
            reasons.append(f"monte-carlo ruin {outcome.ruin_probability:.2f} > {t.max_ruin_probability}")
        if outcome.overfit:
            reasons.append("overfit risk not LOW")
        if not outcome.passed:
            failed = [s.stage.value for s in outcome.stages if not s.passed]
            reasons.append("failed stages: " + ", ".join(failed))
        return GateResult(passed=not reasons, reasons=reasons or ["all gate conditions satisfied"])
