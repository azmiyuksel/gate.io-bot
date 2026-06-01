"""A/B testing of two strategies on identical data, window and risk constraints.

Both genomes are evaluated over the same period and the same walk-forward
windows, so the comparison is apples-to-apples. The winner is the higher-fitness
strategy; statistical significance is assessed with a Welch t-test on the paired
per-window returns.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.models.entities import ABTestResult
from app.strategy_research.backtest_runner import ResearchBacktestRunner
from app.strategy_research.evaluator import StrategyEvaluator
from app.strategy_research.hypothesis_builder import _welch_t_test
from app.strategy_research.models import EvaluationResult, StrategyGenome


@dataclass
class ABComparison:
    winner: str  # A | B | TIE
    p_value: float
    a: EvaluationResult
    b: EvaluationResult
    detail: str


class ABTester:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.runner = ResearchBacktestRunner(db)
        self.evaluator = StrategyEvaluator()

    def compare(
        self,
        genome_a: StrategyGenome,
        genome_b: StrategyGenome,
        symbol: str = "BTC_USDT",
        timeframe: str = "1h",
        strategy_a_id: int | None = None,
        strategy_b_id: int | None = None,
        persist: bool = True,
    ) -> ABComparison | None:
        a = self.runner.evaluate(genome_a, symbol, timeframe)
        b = self.runner.evaluate(genome_b, symbol, timeframe)
        if a is None or b is None:
            return None
        self.evaluator.score(a)
        self.evaluator.score(b)

        # Paired per-window returns -> significance of the performance gap.
        a_returns = np.array([w.total_return for w in a.walk_forward], dtype="float64")
        b_returns = np.array([w.total_return for w in b.walk_forward], dtype="float64")
        p_value = _welch_t_test(a_returns, b_returns) if a_returns.size and b_returns.size else 1.0

        if abs(a.fitness - b.fitness) < 1e-6:
            winner = "TIE"
        else:
            winner = "A" if a.fitness > b.fitness else "B"
        detail = (
            f"A fitness={a.fitness:.3f} (sharpe={a.sharpe:.2f}), "
            f"B fitness={b.fitness:.3f} (sharpe={b.sharpe:.2f}), p={p_value:.3f}"
        )

        if persist:
            self.db.add(
                ABTestResult(
                    strategy_a_id=strategy_a_id,
                    strategy_b_id=strategy_b_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    winner=winner,
                    a_metrics=a.metrics,
                    b_metrics=b.metrics,
                    a_fitness=round(a.fitness, 6),
                    b_fitness=round(b.fitness, 6),
                    p_value=round(p_value, 6),
                    detail=detail,
                )
            )
            self.db.commit()

        return ABComparison(winner=winner, p_value=p_value, a=a, b=b, detail=detail)
