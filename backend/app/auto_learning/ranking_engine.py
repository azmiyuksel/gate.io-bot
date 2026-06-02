"""Weighted 0-100 strategy ranking and persistence.

score = 30*robustness + 25*walk_forward + 20*stability + 15*sharpe + 10*drawdown
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.auto_learning.models import RankingBreakdown, compute_ranking
from app.models.entities import StrategyRanking


class RankingEngine:
    def __init__(self, db: Session) -> None:
        self.db = db

    def rank(
        self,
        *,
        sharpe: float,
        stability: float,
        consistency: float,
        max_drawdown: float,
        ruin_probability: float,
        overfit: bool,
    ) -> RankingBreakdown:
        return compute_ranking(
            sharpe=sharpe,
            stability=stability,
            consistency=consistency,
            max_drawdown=max_drawdown,
            ruin_probability=ruin_probability,
            overfit=overfit,
        )

    def persist(
        self, strategy_id: int, version_id: int | None, breakdown: RankingBreakdown,
        cycle_id: int | None = None,
    ) -> StrategyRanking:
        ranking = StrategyRanking(
            strategy_id=strategy_id,
            version_id=version_id,
            score=Decimal(str(round(breakdown.total, 2))),
            robustness=Decimal(str(round(breakdown.robustness, 2))),
            walk_forward=Decimal(str(round(breakdown.walk_forward, 2))),
            stability=Decimal(str(round(breakdown.stability, 2))),
            sharpe=Decimal(str(round(breakdown.sharpe, 2))),
            drawdown=Decimal(str(round(breakdown.drawdown, 2))),
            cycle_id=cycle_id,
        )
        self.db.add(ranking)
        self.db.commit()
        self.db.refresh(ranking)
        return ranking

    def leaderboard(self, limit: int = 25) -> list[StrategyRanking]:
        return (
            self.db.query(StrategyRanking)
            .order_by(StrategyRanking.score.desc(), StrategyRanking.created_at.desc())
            .limit(limit)
            .all()
        )
