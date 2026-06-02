from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class LearningRunIn(BaseModel):
    symbol: str = "BTC_USDT"
    timeframe: str = "1h"
    population: int | None = None


class LearningRunOut(BaseModel):
    cycle_id: int
    status: str
    patterns_found: int
    hypotheses_generated: int
    features_discovered: int
    strategies_evolved: int
    strategies_validated: int
    promotion_requests: int
    safety_invariants_held: bool


class LearningStatusOut(BaseModel):
    enabled: bool
    latest_cycle: dict | None
    pending_approvals: int
    knowledge: dict
    safety_invariants: list[str]


class KnowledgeEntryOut(BaseModel):
    id: int
    knowledge_type: str
    title: str
    description: str
    symbol: str
    regime: str | None
    confidence: Decimal
    support: int
    created_at: datetime

    class Config:
        from_attributes = True


class DiscoveredFeatureOut(BaseModel):
    id: int
    name: str
    formula: str
    symbol: str
    timeframe: str
    correlation_with_profit: Decimal
    importance_score: Decimal
    stability_score: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class StrategyRankingOut(BaseModel):
    id: int
    strategy_id: int
    version_id: int | None
    score: Decimal
    robustness: Decimal
    walk_forward: Decimal
    stability: Decimal
    sharpe: Decimal
    drawdown: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class PromotionRequestOut(BaseModel):
    id: int
    strategy_id: int
    version_id: int | None
    status: str
    ranking_score: Decimal
    gate_passed: bool
    gate_reasons: list
    validation: dict
    requested_by: str
    decided_by: str | None
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None

    class Config:
        from_attributes = True


class HypothesisOut(BaseModel):
    id: int
    statement: str
    feature: str
    condition: str
    status: str
    supported: bool
    edge: Decimal
    p_value: Decimal
    sample_size: int
    created_at: datetime

    class Config:
        from_attributes = True


class LearningCycleOut(BaseModel):
    id: int
    status: str
    symbol: str
    timeframe: str
    patterns_found: int
    hypotheses_generated: int
    features_discovered: int
    strategies_evolved: int
    strategies_validated: int
    promotion_requests: int
    started_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


class DecisionIn(BaseModel):
    decided_by: str
    note: str | None = None
