"""Central knowledge base - the system's long-term memory.

Aggregates everything the platform has learned (strategies, trades, regime
performance, feature performance, walk-forward / Monte-Carlo outcomes) and stores
distilled insights as ``KnowledgeEntry`` rows. Other components read from it to
seed evolution and to avoid re-learning known facts.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.auto_learning.models import KnowledgeType
from app.models.entities import (
    FeatureRecord,
    KnowledgeEntry,
    RegimePerformance,
    StrategyVersion,
    Trade,
)


class KnowledgeBase:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- write ---
    def record(
        self,
        knowledge_type: KnowledgeType,
        title: str,
        description: str,
        *,
        symbol: str = "BTC_USDT",
        regime: str | None = None,
        confidence: float = 0.5,
        support: int = 0,
        payload: dict | None = None,
        cycle_id: int | None = None,
    ) -> KnowledgeEntry:
        entry = KnowledgeEntry(
            knowledge_type=str(knowledge_type),
            title=title[:255],
            description=description,
            symbol=symbol,
            regime=regime,
            confidence=Decimal(str(round(max(0.0, min(1.0, confidence)), 4))),
            support=support,
            payload=payload or {},
            cycle_id=cycle_id,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    # --- read ---
    def query(
        self, knowledge_type: KnowledgeType | None = None, regime: str | None = None, limit: int = 100
    ) -> list[KnowledgeEntry]:
        q = self.db.query(KnowledgeEntry)
        if knowledge_type is not None:
            q = q.filter(KnowledgeEntry.knowledge_type == str(knowledge_type))
        if regime is not None:
            q = q.filter(KnowledgeEntry.regime == regime)
        return q.order_by(KnowledgeEntry.created_at.desc()).limit(limit).all()

    def successful_parameters(self, limit: int = 5) -> list[dict]:
        """Top evaluated strategy parameter sets, to seed evolution."""
        versions = (
            self.db.query(StrategyVersion)
            .filter(StrategyVersion.overfit.is_(False))
            .order_by(StrategyVersion.fitness.desc())
            .limit(limit)
            .all()
        )
        return [v.parameters for v in versions if v.parameters]

    def regime_performance(self) -> list[RegimePerformance]:
        return self.db.query(RegimePerformance).all()

    def top_features(self, symbol: str = "BTC_USDT", timeframe: str = "1h", limit: int = 10) -> list[FeatureRecord]:
        return (
            self.db.query(FeatureRecord)
            .filter(FeatureRecord.symbol == symbol)
            .filter(FeatureRecord.timeframe == timeframe)
            .order_by(FeatureRecord.importance_score.desc())
            .limit(limit)
            .all()
        )

    def closed_trades(self, limit: int = 1000) -> list[Trade]:
        return (
            self.db.query(Trade)
            .order_by(Trade.traded_at.desc())
            .limit(limit)
            .all()
        )

    def stats(self) -> dict:
        return {
            "knowledge_entries": self.db.query(KnowledgeEntry).count(),
            "strategy_versions": self.db.query(StrategyVersion).count(),
            "trades": self.db.query(Trade).count(),
            "regime_records": self.db.query(RegimePerformance).count(),
            "features": self.db.query(FeatureRecord).count(),
        }
