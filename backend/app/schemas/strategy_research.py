from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class GenerateIn(BaseModel):
    template: str = "ema_rsi_atr"
    symbol: str = "BTC_USDT"
    timeframe: str = "1h"
    feature_driven: bool = False
    evaluate: bool = True


class RunIn(BaseModel):
    symbol: str = "BTC_USDT"
    timeframe: str = "1h"
    population: int | None = None


class RunOut(BaseModel):
    evaluated: int
    promoted: int
    best_fitness: float
    best_strategy_id: int | None = None
    best_sharpe: float | None = None
    reason: str | None = None
    leaderboard: list[dict]


class StrategyVersionOut(BaseModel):
    id: int
    strategy_id: int
    version: int
    parameters: dict
    sharpe: Decimal
    profit_factor: Decimal
    max_drawdown: Decimal
    stability_score: Decimal
    consistency_score: Decimal
    fitness: Decimal
    overfit: bool
    total_trades: int
    created_at: datetime

    class Config:
        from_attributes = True


class ResearchStrategyOut(BaseModel):
    id: int
    name: str
    template: str
    status: str
    origin: str
    family_id: int | None
    best_fitness: Decimal
    best_version_id: int | None
    parameters: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExperimentOut(BaseModel):
    id: int
    experiment_type: str
    status: str
    strategy_id: int | None
    symbol: str
    timeframe: str
    result: dict
    fitness: Decimal
    created_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


class FeatureRecordOut(BaseModel):
    id: int
    name: str
    category: str
    symbol: str
    timeframe: str
    importance_score: Decimal
    correlation_with_profit: Decimal
    stability_score: Decimal
    updated_at: datetime

    class Config:
        from_attributes = True


class HypothesisTestOut(BaseModel):
    id: int
    statement: str
    feature: str
    condition: str
    status: str
    supported: bool
    edge: Decimal
    p_value: Decimal
    sample_size: int
    result: dict
    symbol: str
    timeframe: str
    created_at: datetime

    class Config:
        from_attributes = True


class ABTestOut(BaseModel):
    id: int
    strategy_a_id: int | None
    strategy_b_id: int | None
    symbol: str
    timeframe: str
    winner: str
    a_fitness: Decimal
    b_fitness: Decimal
    p_value: Decimal
    detail: str
    created_at: datetime

    class Config:
        from_attributes = True


class PromotionOut(BaseModel):
    strategy_id: int
    decision: str
    passed: bool
    reasons: list[str]


class StrategyDetailOut(BaseModel):
    strategy: ResearchStrategyOut
    versions: list[StrategyVersionOut]
    trades: list[dict]
    equity_curve: list[dict]

    class Config:
        from_attributes = True


class CustomHypothesisIn(BaseModel):
    statement: str
    feature: str
    condition_desc: str
    expects_negative: bool = False
    symbol: str = "BTC_USDT"
    timeframe: str = "1h"


class SymbolOut(BaseModel):
    symbol: str
    has_data: bool
