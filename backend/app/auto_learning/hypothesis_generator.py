"""Generates and tests new market hypotheses.

Reuses the research lab's statistically-grounded HypothesisBuilder (Welch t-test
on conditional forward returns) and promotes supported hypotheses into the
knowledge base so evolution and reporting can use them.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.auto_learning.knowledge_base import KnowledgeBase
from app.auto_learning.models import KnowledgeType
from app.models.entities import HypothesisTest
from app.strategy_research.hypothesis_builder import HypothesisBuilder


class HypothesisGenerator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.builder = HypothesisBuilder(db)
        self.kb = KnowledgeBase(db)

    def generate_and_test(
        self, symbol: str = "BTC_USDT", timeframe: str = "1h", cycle_id: int | None = None
    ) -> list[HypothesisTest]:
        records = self.builder.test_all(symbol, timeframe)
        for rec in records:
            if rec.supported:
                self.kb.record(
                    KnowledgeType.pattern,
                    f"Validated hypothesis: {rec.feature}",
                    f"{rec.statement} (edge={float(rec.edge):.4f}, p={float(rec.p_value):.3f}, n={rec.sample_size})",
                    symbol=symbol,
                    confidence=max(0.0, 1.0 - float(rec.p_value)),
                    support=rec.sample_size,
                    cycle_id=cycle_id,
                    payload={"edge": float(rec.edge), "p_value": float(rec.p_value)},
                )
        return records
