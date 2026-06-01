"""Persistence for the research lab (strategies, versions, experiments).

De-duplicates strategies by genome signature, versions each re-evaluation and
keeps the strategy's best fitness/version in sync.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import (
    ResearchExperiment,
    ResearchStrategy,
    StrategyVersion,
)
from app.strategy_research.models import (
    EvaluationResult,
    ExperimentStatus,
    ExperimentType,
    StrategyGenome,
    StrategyStatus,
)


class ResearchRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_strategy(self, genome: StrategyGenome) -> tuple[ResearchStrategy, bool]:
        signature = genome.signature()
        existing = (
            self.db.query(ResearchStrategy)
            .filter(ResearchStrategy.signature == signature)
            .first()
        )
        if existing is not None:
            return existing, False

        strategy = ResearchStrategy(
            name=f"{genome.template}-{abs(hash(signature)) % 100000:05d}",
            template=genome.template,
            signature=signature,
            status=str(StrategyStatus.candidate),
            origin=genome.origin,
            parameters=genome.parameters,
        )
        self.db.add(strategy)
        self.db.commit()
        self.db.refresh(strategy)
        return strategy, True

    def add_version(self, strategy: ResearchStrategy, result: EvaluationResult) -> StrategyVersion:
        count = (
            self.db.query(StrategyVersion)
            .filter(StrategyVersion.strategy_id == strategy.id)
            .count()
        )
        version = StrategyVersion(
            strategy_id=strategy.id,
            version=count + 1,
            parameters=result.genome.parameters,
            metrics=result.metrics,
            walk_forward=[asdict(w) for w in result.walk_forward],
            monte_carlo=result.monte_carlo,
            sharpe=Decimal(str(round(result.sharpe, 6))),
            profit_factor=Decimal(str(round(result.profit_factor, 6))),
            max_drawdown=Decimal(str(round(result.max_drawdown, 6))),
            stability_score=Decimal(str(round(result.stability_score, 6))),
            consistency_score=Decimal(str(round(result.consistency_score, 6))),
            fitness=Decimal(str(round(result.fitness, 6))),
            overfit=result.overfit,
            total_trades=result.total_trades,
        )
        self.db.add(version)
        self.db.flush()

        if strategy.best_version_id is None or result.fitness > float(strategy.best_fitness):
            strategy.best_fitness = Decimal(str(round(result.fitness, 6)))
            strategy.best_version_id = version.id
        strategy.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(version)
        return version

    def set_status(self, strategy: ResearchStrategy, status: StrategyStatus) -> None:
        strategy.status = str(status)
        strategy.updated_at = datetime.now(UTC)
        self.db.commit()

    def record_experiment(
        self,
        experiment_type: ExperimentType,
        *,
        status: ExperimentStatus = ExperimentStatus.completed,
        strategy_id: int | None = None,
        symbol: str = "BTC_USDT",
        timeframe: str = "1h",
        config: dict | None = None,
        result: dict | None = None,
        fitness: float = 0.0,
        error: str | None = None,
    ) -> ResearchExperiment:
        experiment = ResearchExperiment(
            experiment_type=str(experiment_type),
            status=str(status),
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            config=config or {},
            result=result or {},
            fitness=Decimal(str(round(fitness, 6))),
            error=error,
            completed_at=datetime.now(UTC) if status == ExperimentStatus.completed else None,
        )
        self.db.add(experiment)
        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    def leaderboard(self, limit: int = 25) -> list[StrategyVersion]:
        return (
            self.db.query(StrategyVersion)
            .order_by(StrategyVersion.fitness.desc())
            .limit(limit)
            .all()
        )
