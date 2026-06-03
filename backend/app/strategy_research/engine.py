"""Strategy Research Engine - orchestrates the evolutionary research loop.

generate -> evaluate (backtest + walk-forward + Monte Carlo) -> score -> rank ->
breed (crossover + mutation) -> gate -> promote/reject. Designed to be driven
repeatedly by the scheduler as a continuous research loop, persisting every
strategy, version and experiment.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import ResearchStrategy, StrategyVersion
from app.strategy_research.backtest_runner import ResearchBacktestRunner
from app.strategy_research.evaluator import PromotionVerdict, StrategyEvaluator
from app.strategy_research.feature_store import FeatureStore
from app.strategy_research.generator import StrategyGenerator
from app.strategy_research.models import (
    EvaluationResult,
    ExperimentType,
    PromotionDecision,
    StrategyGenome,
    StrategyStatus,
    WalkForwardWindowResult,
)
from app.strategy_research.repository import ResearchRepository

logger = logging.getLogger(__name__)


class StrategyResearchEngine:
    def __init__(self, db: Session, seed: int | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.generator = StrategyGenerator(seed)
        self.runner = ResearchBacktestRunner(db)
        self.evaluator = StrategyEvaluator(self.settings)
        self.repo = ResearchRepository(db)
        self.feature_store = FeatureStore(db)

    # ------------------------------------------------------------------
    # Spec API
    # ------------------------------------------------------------------
    def generate_strategy(
        self, template: str = "ema_rsi_atr", feature_driven: bool = False,
        symbol: str = "BTC_USDT", timeframe: str = "1h",
    ) -> StrategyGenome:
        if feature_driven:
            importances = self.feature_store.importances(symbol, timeframe)
            if importances:
                return self.generator.generate_feature_driven(importances, template)
        return self.generator.generate(template, 1)[0]

    def mutate_strategy(self, genome: StrategyGenome) -> StrategyGenome:
        return self.generator.mutate(genome)

    def evaluate_strategy(
        self, genome: StrategyGenome, symbol: str = "BTC_USDT", timeframe: str = "1h"
    ) -> tuple[ResearchStrategy, StrategyVersion, EvaluationResult] | None:
        result = self.runner.evaluate(genome, symbol, timeframe, self.settings.research_wf_windows)
        if result is None:
            return None
        self.evaluator.score(result)
        strategy, _ = self.repo.get_or_create_strategy(genome)
        version = self.repo.add_version(strategy, result)
        self.repo.record_experiment(
            ExperimentType.evaluation,
            strategy_id=strategy.id,
            symbol=symbol,
            timeframe=timeframe,
            config={"parameters": genome.parameters},
            result={
                "sharpe": result.sharpe,
                "max_drawdown": result.max_drawdown,
                "consistency": result.consistency_score,
                "overfit": result.overfit,
            },
            fitness=result.fitness,
        )
        return strategy, version, result

    def rank_strategies(self, limit: int = 25) -> list[StrategyVersion]:
        return self.repo.leaderboard(limit)

    def promote_to_production(self, strategy_id: int) -> PromotionVerdict:
        strategy = self.db.get(ResearchStrategy, strategy_id)
        if strategy is None:
            return PromotionVerdict(PromotionDecision.rejected, False, ["strategy not found"])
        version = (
            self.db.get(StrategyVersion, strategy.best_version_id)
            if strategy.best_version_id
            else None
        )
        if version is None:
            return PromotionVerdict(PromotionDecision.rejected, False, ["no evaluated version"])

        verdict = self.evaluator.evaluate_promotion(self._result_from_version(strategy, version))
        new_status = StrategyStatus.promoted if verdict.passed else StrategyStatus.rejected
        self.repo.set_status(strategy, new_status)
        return verdict

    # ------------------------------------------------------------------
    # Research loop (one generation)
    # ------------------------------------------------------------------
    def run_experiments(
        self, symbol: str = "BTC_USDT", timeframe: str = "1h", population: int | None = None
    ) -> dict:
        population = population or self.settings.research_population
        survivors_n = self.settings.research_survivors

        # Refresh feature importances so feature-driven generation has signal.
        try:
            self.feature_store.compute(symbol, timeframe)
        except Exception:
            logger.warning("Feature-store recompute failed", exc_info=True)

        # 1. Build a diverse population (seed + random + feature-driven).
        genomes: list[StrategyGenome] = [self.generator.seed_genome(template_name="ema_rsi_atr")]
        genomes += self.generator.generate("ema_rsi_atr", max(population - 2, 1))
        genomes.append(self.generate_strategy(feature_driven=True, symbol=symbol, timeframe=timeframe))

        evaluated: list[tuple[ResearchStrategy, EvaluationResult]] = []
        for genome in genomes:
            outcome = self.evaluate_strategy(genome, symbol, timeframe)
            if outcome is not None:
                strategy, _, result = outcome
                evaluated.append((strategy, result))

        if not evaluated:
            return {
                "evaluated": 0, "promoted": 0, "best_fitness": 0.0,
                "reason": "insufficient historical data", "leaderboard": [],
            }

        # 2. Rank and breed survivors (crossover + mutation).
        evaluated.sort(key=lambda pair: pair[1].fitness, reverse=True)
        survivors = evaluated[:survivors_n]
        for i in range(len(survivors) - 1):
            child = self.generator.crossover(survivors[i][1].genome, survivors[i + 1][1].genome)
            self.evaluate_strategy(self.generator.mutate(child), symbol, timeframe)

        # 3. Auto-promote any survivor that clears the production gate.
        promoted = 0
        for strategy, result in survivors:
            verdict = self.evaluator.evaluate_promotion(result)
            if verdict.passed:
                self.repo.set_status(strategy, StrategyStatus.promoted)
                promoted += 1

        best = evaluated[0]
        return {
            "evaluated": len(evaluated),
            "promoted": promoted,
            "best_fitness": round(best[1].fitness, 4),
            "best_strategy_id": best[0].id,
            "best_sharpe": round(best[1].sharpe, 4),
            "leaderboard": [
                {"strategy_id": s.id, "name": s.name, "fitness": round(r.fitness, 4),
                 "sharpe": round(r.sharpe, 4), "overfit": r.overfit}
                for s, r in evaluated[:10]
            ],
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _result_from_version(
        self, strategy: ResearchStrategy, version: StrategyVersion
    ) -> EvaluationResult:
        genome = StrategyGenome(template=strategy.template, parameters=version.parameters)
        wf = [WalkForwardWindowResult(**w) for w in (version.walk_forward or [])]
        return EvaluationResult(
            genome=genome,
            metrics=version.metrics or {},
            monte_carlo=version.monte_carlo or {},
            walk_forward=wf,
            sharpe=float(version.sharpe),
            profit_factor=float(version.profit_factor),
            max_drawdown=float(version.max_drawdown),
            stability_score=float(version.stability_score),
            consistency_score=float(version.consistency_score),
            in_sample_sharpe=0.0,
            out_sample_sharpe=0.0,
            overfit=bool(version.overfit),
            total_trades=int(version.total_trades),
            fitness=float(version.fitness),
        )
