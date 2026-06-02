"""Meta-learning: learns *about* strategies, regimes and the portfolio.

Answers higher-order questions - which strategy family works in which regime,
which features stay useful, which allocations are healthy - and emits a
``strategy_family_score`` plus knowledge-base insights. Integrates read-only with
the Market Regime Detector and Portfolio Manager outputs.
"""
from __future__ import annotations

import statistics

from sqlalchemy.orm import Session

from app.auto_learning.knowledge_base import KnowledgeBase
from app.auto_learning.models import KnowledgeType
from app.models.entities import PortfolioMetric, RegimePerformance


class MetaLearning:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.kb = KnowledgeBase(db)

    def learn(self, symbol: str = "BTC_USDT", cycle_id: int | None = None) -> dict:
        regime_leaders = self._regime_learning(symbol, cycle_id)
        family_scores = self._family_scores(symbol, cycle_id)
        portfolio = self._portfolio_learning(symbol, cycle_id)
        return {
            "regime_leaders": regime_leaders,
            "family_scores": family_scores,
            "portfolio": portfolio,
        }

    def _regime_learning(self, symbol: str, cycle_id: int | None) -> dict[str, str]:
        rows = self.db.query(RegimePerformance).all()
        leaders: dict[str, str] = {}
        best: dict[str, RegimePerformance] = {}
        for row in rows:
            cur = best.get(row.regime_type)
            if cur is None or float(row.profit_factor) > float(cur.profit_factor):
                best[row.regime_type] = row
        for regime, row in best.items():
            leaders[regime] = row.strategy_name
        return leaders

    def _family_scores(self, symbol: str, cycle_id: int | None) -> dict[str, float]:
        """Score each strategy family (by name) from its cross-regime profit factor."""
        rows = self.db.query(RegimePerformance).all()
        by_strategy: dict[str, list[float]] = {}
        for row in rows:
            by_strategy.setdefault(row.strategy_name, []).append(float(row.profit_factor))
        scores = {name: round(statistics.fmean(pfs), 4) for name, pfs in by_strategy.items() if pfs}
        for name, score in scores.items():
            self.kb.record(
                KnowledgeType.meta, f"strategy_family_score: {name}",
                f"Average cross-regime profit factor {score:.2f}",
                symbol=symbol, confidence=min(1.0, score / 2), cycle_id=cycle_id,
                payload={"family_score": score},
            )
        return scores

    def _portfolio_learning(self, symbol: str, cycle_id: int | None) -> dict:
        latest = (
            self.db.query(PortfolioMetric)
            .order_by(PortfolioMetric.timestamp.desc())
            .first()
        )
        if latest is None:
            return {}
        insight = {
            "sharpe_ratio": float(latest.sharpe_ratio),
            "correlation_risk_score": float(latest.correlation_risk_score),
            "drawdown": float(latest.drawdown),
        }
        if float(latest.correlation_risk_score) > 0.7:
            self.kb.record(
                KnowledgeType.portfolio, "High portfolio correlation risk",
                f"Correlation risk score {float(latest.correlation_risk_score):.2f} - diversification weak",
                symbol=symbol, confidence=0.8, cycle_id=cycle_id, payload=insight,
            )
        return insight
